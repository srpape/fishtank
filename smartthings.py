#!/usr/bin/env python3

from flask import Flask
from flask import make_response
from flask import request

from flask_restful import Api, Resource, reqparse

from apscheduler.schedulers.background import BackgroundScheduler
from AtlasI2C import AtlasI2C
from w1thermsensor import W1ThermSensor
from collections import deque
from datetime import datetime

import RPi.GPIO as GPIO
import urllib.request
import json
import numpy
import os
import logging

app = Flask(__name__)
api = Api(app)

# TODO: Let the hub provide this via /subscribe
notify_url = 'http://192.168.1.121:39500/notify'
GPIO.setmode(GPIO.BCM)

class Switch:
    def __init__(self, gpio):
        self.__gpio = gpio

        # Prepare GPIO
        GPIO.setup(self.__gpio, GPIO.OUT)
        self.off()

    def off(self):
        GPIO.output(self.__gpio, GPIO.LOW)
        self.state = 'off'

    def on(self):
        GPIO.output(self.__gpio, GPIO.HIGH)
        self.state = 'on'

class Valve:
    def __init__(self, name, gpio, open_precheck=None, open_action=None, close_action=None):
        self.name = name
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
        if self.__open_precheck is not None and not self.__open_precheck():
            app.logger.info('Refusing to open ' + self.name + ' due to precheck')
            return

        # Only one valve can ever be open so we don't blow a fuse
        # Close any other open valves
        for k, k_valve in valves.items():
            if k is not self and k_valve.is_open():
                app.logger.info('Closing ' + k_valve.name + ' to open ' + self.name)
                k_valve.close()
                k_valve.notify()

        self.__switch.on()
        self.state = 'open'
        self.__open_time = datetime.now()
        if self.__open_action is not None:
            self.__open_action()

    def is_open(self):
        return self.state == 'open'

    def notify(self):
        '''
        Push an unsolicited update to SmartThings
        '''
        body = self.__get_body()
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': len(body),
            'Device': 'valve/' + self.name
        }
        req = urllib.request.Request(notify_url, method='NOTIFY', headers=headers, data=body)
        urllib.request.urlopen(req, timeout=15)

    def get_response(self):
        '''
        Get a response for an HTTP GET or POST
        '''
        resp = make_response(self.__get_body())
        resp.headers['Device'] = 'valve/' + self.name
        return resp

    def __get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        message = { 'state': self.state }
        body = json.dumps(message).encode()
        return body

class Light:
    def __init__(self):
        self.__day_light = Switch(23)
        self.__night_light = Switch(25)
        self.name = 'tank'
        self.state = 0

        # Load the initial light state (if possible)
        try:
            with open('/tmp/tank_light_state.txt', 'r') as f:
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
        with open('/tmp/tank_light_state.txt', 'w') as f:
            f.write(str(self.state))

    def get_response(self):
        '''
        Get a response for an HTTP GET or POST
        '''
        resp = make_response(self.__get_body())
        resp.headers['Device'] = 'light/' + self.name
        return resp

    def notify(self):
        '''
        Push an unsolicited update to SmartThings
        '''
        body = self.__get_body()
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': len(body),
            'Device': 'light/' + self.name
        }
        req = urllib.request.Request(notify_url, method='NOTIFY', headers=headers, data=body)
        urllib.request.urlopen(req, timeout=15)

    def __get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        message = { 'state': self.state }
        body = json.dumps(message).encode()
        return body

class PHSensor:
    def __init__(self, name, temp_sensor):
        self.__name = name
        self.__sensor = AtlasI2C(address=99)
        self.__ph_readings = deque([], maxlen=5)
        self.__temp_sensor = temp_sensor

    def read(self):
        # Read the temp from our service
        pH = self.__sensor.query('RT,' + str(self.__temp_sensor.readC()))
        if pH.startswith('Command succeeded '):
            pH = float(pH[18:].rstrip("\0"))
            return pH
        return None

    def get_response(self):
        '''
        Get a response for an HTTP GET or POST
        '''
        resp = make_response(self.__get_body())
        resp.headers['Device'] = 'temperature/' + self.__name
        return resp

    def notify(self):
        '''
        Push an unsolicited update to SmartThings
        '''
        body = self.__get_body()
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': len(body),
            'Device': 'ph/' + self.__name
        }
        req = urllib.request.Request(notify_url, method='NOTIFY', headers=headers, data=body)
        urllib.request.urlopen(req, timeout=15)

    def __get_body(self):
        '''
        Get the body we send out for response/notify
        '''
        pH = self.read()
        message = {
            'pH': self.read()
        }
        body = json.dumps(message).encode()
        return body

class TemperatureSensor:
    def __init__(self, name):
        self.__name = name
        self.__sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "02099177ba76")

    def celcius_to_fahrenheit(self, tempC):
        return round((9.0/5.0 * tempC + 32), 2)

    def readC(self):
        # Read the temp from our service
        return self.__sensor.get_temperature(W1ThermSensor.DEGREES_C)

    def readF(self):
        # Read the temp from our service
        return round(self.__sensor.get_temperature(W1ThermSensor.DEGREES_F), 2)

    def get_response(self):
        '''
        Get a response for an HTTP GET or POST
        '''
        resp = make_response(self.__get_body())
        resp.headers['Device'] = 'temperature/' + self.__name
        return resp

    def notify(self):
        '''
        Push an unsolicited update to SmartThings
        '''
        body = self.__get_body()
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': len(body),
            'Device': 'temperature/' + self.__name
        }
        req = urllib.request.Request(notify_url, method='NOTIFY', headers=headers, data=body)
        urllib.request.urlopen(req, timeout=15)

    def __get_body(self):
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

class WaterLevelSensor:
    '''
    Used to check if the tank is full
    '''
    def __init__(self, gpio):
        self.__gpio = gpio
        GPIO.setup(self.__gpio, GPIO.IN)

    def is_full(self):
        return GPIO.input(self.__gpio)

# Prepare scheduler
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

#@scheduler.scheduled_job('interval', id='top_off', minutes=1)
def top_off():
    #app.logger.info("Checking for top off")
    fill_valve = valves['fill']
    drain_valve = valves['drain']
    if not fill_valve.is_open() and not drain_valve.is_open():
        if not water_level_sensor.is_full():
            app.logger.info("Topping off tank")
            fill_valve.open()
            fill_valve.notify()

def close_fill_when_full():
    #app.logger.info("Checking if tank is full")
    if water_level_sensor.is_full():
        app.logger.info("Tank is full, closing fill valve")
        fill_valve = valves['fill']
        fill_valve.close()
        fill_valve.notify()
    elif fill_valve.open_duration() > 1200:
        app.logger.warn("Fill valve open for too long!")
        fill_valve = valves['fill']
        fill_valve.close()
        fill_valve.notify()

# Stop draining the tank
def water_change_drain_complete():
    scheduler.remove_job('water_change_drain_complete')

    drain_valve = valves['drain']
    drain_valve.close()
    drain_valve.notify()

    fill_valve = valves['fill']
    fill_valve.open() # Should auto shut-off when full
    fill_valve.notify()

# Our ThingSpeak API Key
with open(os.path.expanduser('/home/papes/.fishtank_thingspeak_api_key'), 'r') as f:
    thingspeak_api_key = f.read().rstrip()
    thingspeak_base_url = 'https://api.thingspeak.com/update?api_key=%s' % thingspeak_api_key

# Our sensors
temp_sensor = TemperatureSensor('tank')
ph_sensor = PHSensor('tank', temp_sensor)
water_level_sensor = WaterLevelSensor(5)

# Our valves
valves = {
    'drain': Valve('drain', 17),
    'fill': Valve('fill', 27,
        open_precheck= lambda: not water_level_sensor.is_full(),
        open_action = lambda: scheduler.add_job(close_fill_when_full, 'interval', seconds=1, id='close_fill_when_full'),
        close_action = lambda: scheduler.remove_job('close_fill_when_full')
    ),
}

# Our lights
lights = {
    'tank': Light()
}

def log_to_thingspeak():
    tempF = temp_sensor.readF()
    pH = ph_sensor.read()
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
    log_to_thingspeak()

    # Notify SmartThings
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
        return "OK"

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

def change_water():
    if not water_level_sensor.is_full:
        return "Tank not full, politely refusing", 406

    scheduler.add_job(water_change_drain_complete, 'interval', seconds=60, id='water_change_drain_complete')
    drain_valve = valves['drain']
    drain_valve.open()
    drain_valve.notify()
    return "OK"

class Action(Resource):
    def get(self, name):
        if name == 'change_water':
            return change_water()

        return "Action not found", 404

api.add_resource(LightHTTP, "/light/<string:name>")
api.add_resource(Temperature, "/temperature/<string:name>")
api.add_resource(PH, "/ph/<string:name>")
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

