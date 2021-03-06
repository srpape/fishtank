#!/usr/bin/env python3

from flask import Flask
from flask import make_response
from flask import request

from flask_restful import Api, Resource, reqparse

from apscheduler.schedulers.background import BackgroundScheduler
from AtlasI2C import AtlasI2C
from w1thermsensor import W1ThermSensor
from datetime import datetime

import configparser
import RPi.GPIO as GPIO
import urllib.request
import json
import numpy
import os
import logging

config_path = '/etc/tank_monitor.conf'

# Parse configuration
config = configparser.ConfigParser()
config.read(config_path)

# thingspeak config
thingspeak_base_url = ''
if config.has_option('thingspeak', 'api_key'):
    thingspeak_api_key = config.get('thingspeak', 'api_key').strip()
    if thingspeak_api_key:
        thingspeak_base_url = 'https://api.thingspeak.com/update?api_key=%s' % thingspeak_api_key

# smartthings config
smartthings_notify_url = ''
if config.has_option('smartthings', 'notify_url'):
    smartthings_notify_url = config.get('smartthings', 'notify_url')

app = Flask(__name__)
api = Api(app)
GPIO.setmode(GPIO.BCM)

def mail(subject, message):
    FROM="SmartThings@FishTank"
    TO="root"
    message = """\
From: %s
To: %s
Subject: %s

%s
""" % (FROM, TO, subject, message)
    p = os.popen("/usr/sbin/sendmail -t -i", "w")
    p.write(message)
    status = p.close()
    if status != 0:
        print("Sendmail exit status" + str(status))

class Switch:
    def __init__(self, gpio):
        self.__gpio = gpio
        self.__on = False

        # Prepare GPIO
        GPIO.setup(self.__gpio, GPIO.OUT)
        self.off()

    def is_on(self):
        return self.__on

    def off(self):
        GPIO.output(self.__gpio, GPIO.LOW)
        self.__on = False

    def on(self):
        GPIO.output(self.__gpio, GPIO.HIGH)
        self.__on = True

class SmartThingsAPIDevice:
    def __init__(self, device_name, device_type):
        self.device_type = device_type
        self.device_name = device_name
        self.__device_path = self.device_type + '/' + self.device_name

    def notify(self):
        '''
        Push an unsolicited update to SmartThings
        '''
        body = self.get_body()
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': len(body),
            'Device': self.__device_path
        }
        if smartthings_notify_url:
            req = urllib.request.Request(smartthings_notify_url, method='NOTIFY', headers=headers, data=body)
            urllib.request.urlopen(req, timeout=15)

    def get_response(self):
        '''
        Get a response for an HTTP GET or POST
        '''
        resp = make_response(self.get_body())
        resp.headers['Device'] = self.__device_path
        return resp

class Valve(SmartThingsAPIDevice):
    def __init__(self, device_name, gpio, open_precheck=None, open_action=None, close_action=None):
        super(Valve, self).__init__(device_type='valve', device_name=device_name)

        self.__switch = Switch(gpio)
        self.__open_precheck = open_precheck
        self.__open_action = open_action
        self.__close_action = None

        self.close()
        self.notify()

        # Do this after calling close() so we don't run close_action before opening
        self.__close_action = close_action

    def open_duration(self):
        if self.__open_time == 0:
            return 0
        return (datetime.now() - self.__open_time).total_seconds()

    def close(self):
        self.__switch.off()
        self.state = 'closed'
        self.__open_time = 0
        if self.__close_action is not None:
            self.__close_action()

    def open(self):
        # Only one valve can ever be open so we don't blow a fuse
        # Close any other open valves
        for k, k_valve in valves.items():
            if k is not self and k_valve.is_open():
                app.logger.info('Closing ' + k_valve.device_name + ' to open ' + self.device_name)
                k_valve.close()
                k_valve.notify()

        if self.__open_precheck is not None and not self.__open_precheck():
            app.logger.info('Refusing to open ' + self.device_name + ' due to precheck')
            return

        self.__switch.on()
        self.state = 'open'
        self.__open_time = datetime.now()
        if self.__open_action is not None:
            self.__open_action()

    def is_open(self):
        return self.__switch.is_on()

    def get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        message = { 'state': self.state }
        body = json.dumps(message).encode()
        return body

class Light(SmartThingsAPIDevice):
    def __init__(self, device_name):
        super(Light, self).__init__(device_type='light', device_name=device_name)

        self.__day_light = Switch(23)
        self.__night_light = Switch(25)
        self.state = 0
        self.__state_file = '/tmp/' + self.device_name + '_light_state.txt'

        # Load the initial light state (if possible)
        try:
            with open(self.__state_file, 'r') as f:
                self.set_state(int(f.read()))
        except IOError:
             pass

        # Send the initial state to SmartThings
        self.notify()

    def is_on(self):
        return self.state > 0

    def set_state(self, state):
        if state is None:
            return

        # Parse to integer
        state = int(state)

        if state == 0:
            self.__day_light.off()
            self.__night_light.off()
        elif state == 1:
            self.__day_light.off()
            self.__night_light.on()
        elif state == 2:
            self.__day_light.on()
            self.__night_light.off()
        else:
            return

        self.state = state
        with open(self.__state_file, 'w') as f:
            f.write(str(self.state))

    def get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        message = { 'state': self.state }
        body = json.dumps(message).encode()
        return body

class PHSensor(SmartThingsAPIDevice):
    def __init__(self, device_name, temp_sensor):
        super(PHSensor, self).__init__(device_type='ph', device_name=device_name)
        self.__sensor = AtlasI2C(address=99)
        self.__temp_sensor = temp_sensor

    def read(self, tempC=None):
        # Read the temp from our service
        if tempC is None:
            tempC = self.__temp_sensor.readC()

        pH = self.__sensor.query('RT,' + str(tempC))
        if pH.startswith('Command succeeded '):
            pH = float(pH[18:].rstrip("\0"))
            return pH
        return None

    def get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        pH = self.read()
        if pH is not None:
            message = {
                'pH': pH
            }
            body = json.dumps(message).encode()
            return body
        return ''

class TemperatureSensor(SmartThingsAPIDevice):
    def __init__(self, device_name):
        super(TemperatureSensor, self).__init__(device_type='temperature', device_name=device_name)
        self.__sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "02099177ba76")

    def celcius_to_fahrenheit(self, tempC):
        return round((9.0/5.0 * tempC + 32), 2)

    def __read(self):
        readings = []
        for i in range(3):
            readings.append(self.__sensor.get_temperature(W1ThermSensor.DEGREES_C))
            readings.append(self.__sensor.get_temperature(W1ThermSensor.DEGREES_C))
        return round(numpy.median(readings), 3)

    def readC(self):
        return self.__read()

    def readF(self):
        tempC = self.readC()
        tempF = self.celcius_to_fahrenheit(tempC)
        return tempF

    def get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        tempC = self.readC()
        tempF = self.celcius_to_fahrenheit(tempC)
        message = {
            'temperatureC': tempC,
            'temperatureF': tempF,
        }
        body = json.dumps(message).encode()
        return body

class WaterLevelSensor(SmartThingsAPIDevice):
    '''
    Used to check if the tank is full
    '''
    def __init__(self, device_name, gpio):
        super(WaterLevelSensor, self).__init__(device_type='water_level', device_name=device_name)
        self.__gpio = gpio
        GPIO.setup(self.__gpio, GPIO.IN)

    def is_full(self):
        return GPIO.input(self.__gpio)

    def get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        message = {
            'state': self.is_full(),
        }
        body = json.dumps(message).encode()
        return body

# Prepare scheduler
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

auto_fill_locked_out = False

default_max_fill_time = 60 * 2 # 2 minutes

current_max_fill_time = default_max_fill_time

# Our sensors
temp_sensor = TemperatureSensor('tank')
ph_sensor = PHSensor('tank', temp_sensor)
water_level_sensor = WaterLevelSensor('tank', 5)

@scheduler.scheduled_job('interval', id='top_off', minutes=5)
def top_off():
    global current_max_fill_time

    if not water_level_sensor.is_full():
        # Don't run if we've had a timeout error
        if auto_fill_locked_out:
            app.logger.warn("Auto-fill locked out, not filling")
            return

        fill_valve = valves['fill']
        drain_valve = valves['drain']
        if not fill_valve.is_open() and not drain_valve.is_open():
            app.logger.info("Topping off tank")
            current_max_fill_time = 15 # 15 seconds should be plenty for a top off
            fill_valve.open()
            fill_valve.notify()

def close_drain_after_timeout():
    app.logger.warn('Closing drain after timeout')
    drain_valve = valves['drain']
    drain_valve.close()
    drain_valve.notify()
    mail('Drain timeout', 'Closing drain after timeout')

def close_fill_when_full():
    global auto_fill_locked_out
    global current_max_fill_time

    #app.logger.info("Checking if tank is full")
    fill_valve = valves['fill']
    water_level_sensor.notify()
    if water_level_sensor.is_full():
        app.logger.info("Tank is full, closing fill valve")
        auto_fill_locked_out = False
        fill_valve.close()
        fill_valve.notify()

        # Restore this to the default
        current_max_fill_time = default_max_fill_time
    elif fill_valve.open_duration() > current_max_fill_time:
        app.logger.warn("Fill valve open for too long!")
        auto_fill_locked_out = True
        fill_valve.close()
        fill_valve.notify()
        mail('Fill timeout', 'Closing fill after timeout')

# Stop draining the tank
def water_change_drain_complete():
    scheduler.remove_job('water_change_drain_complete')

    app.logger.info("Water drain complete, starting fill...")

    # TODO: If the user closes the drain early, close() throws an exception trying to run the close action
    drain_valve = valves['drain']
    drain_valve.close()
    drain_valve.notify()

    fill_valve = valves['fill']
    fill_valve.open() # Should auto shut-off when full
    fill_valve.notify()

def on_fill_close():
    global current_max_fill_time
    current_max_fill_time = default_max_fill_time
    scheduler.remove_job('close_fill_when_full')

# Our valves
valves = {
    'drain': Valve('drain', 17,
        # On open, we start a 5 minute timer
        # If the valve is still open at the end of the timer, close it for safety
        open_action = lambda: scheduler.add_job(close_drain_after_timeout, 'interval', seconds=300, id='close_drain_after_timeout'),
        close_action = lambda: scheduler.remove_job('close_drain_after_timeout')
    ),
    'fill': Valve('fill', 27,
        # On open, we first check that the tank isn't already full
        # We also check every second to make sure the tank hasn't filled up
        # close_fill_when_full will also close the fill valve if left open for too long.
        open_precheck= lambda: not water_level_sensor.is_full(),
        open_action = lambda: scheduler.add_job(close_fill_when_full, 'interval', seconds=3, id='close_fill_when_full'),
        close_action = on_fill_close
    ),
}

# Our lights
lights = {
    'tank': Light('tank')
}

def log_to_thingspeak():
    tempC = temp_sensor.readC()
    tempF = temp_sensor.celcius_to_fahrenheit(tempC)
    pH = ph_sensor.read(tempC)
    try:
        f = urllib.request.urlopen(thingspeak_base_url + "&field1=%s&field2=%s" % (str(tempF), str(pH)), timeout=15)
        f.close()
    except Exception:
        # For some reason the data was not accepted
        # ThingSpeek gives a lot of 500 errors
        pass

@scheduler.scheduled_job('cron', id='log_to_cloud', minute='*')
def log_to_cloud():
    # Notify ThingSpeak
    if thingspeak_base_url:
        log_to_thingspeak()

    # Notify SmartThings
    water_level_sensor.notify()
    temp_sensor.notify()
    ph_sensor.notify()

class Temperature(Resource):
    def get(self, name):
        if(name == "tank"):
            return temp_sensor.get_response()

        return "Temperature sensor not found", 404

class PH(Resource):
    def get(self, name):
        if(name == "tank"):
            return ph_sensor.get_response()

        return "pH sensor not found", 404

class WaterLevel(Resource):
    def get(self, name):
        if(name == "tank"):
            return water_level_sensor.get_response()

        return "pH sensor not found", 404

class ValveHTTP(Resource):
    def get(self, name):
        valve = valves.get(name)
        if valve is not None:
            return valve.get_response()

        return "Valve not found", 404

    def post(self, name):
        # Parse arguments
        parser = reqparse.RequestParser()
        parser.add_argument("state")
        args = parser.parse_args()

        # Get arguments
        state = args.get('state')

        # Get the target valve
        valve = valves.get(name)
        if not valve:
            return "Valve not found", 404

        # Check the desired action
        if state == 'open':
            # Open the target valve
            valve.open()
        elif state == 'closed':
            # Close the target valve
            valve.close()
        else:
            return "Invalid State", 400

        # Return the valve's response
        return valve.get_response()


class Subscription(Resource):
    def get(self, name):
        global smartthings_notify_url

        # Update our NOTIFY URL for posting events to SmartThings
        new_smartthings_notify_url = 'http://' + name.strip()
        if new_smartthings_notify_url != smartthings_notify_url:
            smartthings_notify_url = new_smartthings_notify_url
            # Update our config file
            if not config.has_section('smartthings'):
                config.add_section('smartthings')
            config.set('smartthings', 'notify_url', smartthings_notify_url)
            # Write it back out
            with open(config_path, 'w') as f:
                config.write(f)

class LightHTTP(Resource):
    def get(self, name):
        light = lights.get(name)
        if not light:
            return "Light not found", 404

        return light.get_response()

    def post(self, name):
        # Parse arguments
        parser = reqparse.RequestParser()
        parser.add_argument('state')
        args = parser.parse_args()

        # Get the light
        light = lights.get(name)
        if not light:
            return "Light not found", 404

        # Get arguments
        state = args.get('state')

        light.set_state(state)
        return light.get_response()

def change_water(time : int = None):
    global current_max_fill_time

    if not water_level_sensor.is_full:
        return "Tank not full, politely refusing", 406

    if auto_fill_locked_out:
        app.logger.info("Auto-fill is locked due to error, refusing water change")
        return "Auto-fill is locked due to error, refusing water change", 500

    if time is None:
        time = 60 * 2 # 2 minutes

    app.logger.info("Starting " + str(time) + " second water change")

    # How long (at most) we want to run the fill up
    current_max_fill_time = 60 * 18 # 18 minutes

    scheduler.add_job(water_change_drain_complete, 'interval', seconds=time, id='water_change_drain_complete')
    drain_valve = valves['drain']
    drain_valve.open()
    drain_valve.notify()
    return "OK"

class Action(Resource):
    def post(self, name):
        if name == 'change_water':
            parser = reqparse.RequestParser()
            parser.add_argument('time')
            args = parser.parse_args()
            time = args.get('time')

            return change_water(time)

        return "Action not found", 404

api.add_resource(LightHTTP, "/light/<string:name>")
api.add_resource(Temperature, "/temperature/<string:name>")
api.add_resource(PH, "/ph/<string:name>")
api.add_resource(WaterLevel, "/water_level/<string:name>")
api.add_resource(ValveHTTP, "/valve/<string:name>")
api.add_resource(Subscription, "/subscribe/<string:name>")
api.add_resource(Action, "/action/<string:name>")

try:
    # With the reloader enabled, apscheduler executes twice, one in each process
    # We could probably fix this correctly, but just disabling the reloader for now
    app.run(debug=True,host='0.0.0.0', use_reloader=False)
finally:
    print("GPIO Cleanup")
    GPIO.cleanup()

