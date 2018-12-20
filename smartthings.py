#!/usr/bin/env python3

from flask import Flask
from flask import make_response
from flask import request

from flask_restful import Api, Resource, reqparse

from apscheduler.schedulers.background import BackgroundScheduler
from AtlasI2C import AtlasI2C
from w1thermsensor import W1ThermSensor
from collections import deque

import RPi.GPIO as GPIO
import urllib.request
import json
import numpy
import os

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
    def __init__(self, name, gpio):
        self.name = name
        self.__switch = Switch(gpio)

        self.close()
        self.notify()

    def close(self):
        self.__switch.off()
        self.state = 'closed'

    def open(self):
        self.__switch.on()
        self.state = 'open'

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
        pH = self.__sensor.query('RT,' + str(self.__temp_sensor.read()))
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

    def update(self):
        pH = self.__sensor.query('RT,' + str(self.__temp_sensor.read()))
        if pH.startswith('Command succeeded '):
            pH = float(pH[18:].rstrip("\0"))
            self.__ph_readings.append(pH)

class TemperatureSensor:
    def __init__(self, name):
        self.__name = name
        self.__sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "02099177ba76")

    def celcius_to_fahrenheit(self, tempC):
        return round((9.0/5.0 * tempC + 32), 2)

    def read(self):
        # Read the temp from our service
        return self.__sensor.get_temperature(W1ThermSensor.DEGREES_C)

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
        tempC = self.read()
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
    'fill': Valve('fill', 27),
}

# Our lights
lights = {
    'tank': Light()
}

# Prepare scheduler
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

def close_fill_when_full():
    print("Checking if full")
    if water_level_sensor.is_full():
        valve = valves['fill']
        valve.close()
        valve.notify()
        scheduler.remove_job('close_fill_when_full')

def log_to_thingspeak():
    tempC = temp_sensor.read()
    tempF = temp_sensor.celcius_to_fahrenheit(tempC)
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
            # Turn off any other valves first so we don't blow a fuse
            for k, k_valve in valves.items():
                if k != valve.name and k_valve.is_open():
                    k_valve.close()
                    k_valve.notify()

            # Special handling for the fill valve
            if name == 'fill':
                # Don't open it if the tank is full
                if not water_level_sensor.is_full():
                    # Allow the valve to open
                    valve.open()

                    # Start monitoring for a full tank
                    scheduler.add_job(close_fill_when_full, 'interval', seconds=1, id='close_fill_when_full')
                else:
                    print('Refusing to open fill valve on a full tank!')
            else:
                # Special handling for the fill valve
                if name == 'fill':
                    scheduler.remove_job('close_fill_when_full')

                # Open the target valve
                valve.open()
        elif state == 'closed':
            # Close the target valve
            valve.close()
        else:
            return "Invalid State"

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

api.add_resource(LightHTTP, "/light/<string:name>")
api.add_resource(Temperature, "/temperature/<string:name>")
api.add_resource(PH, "/ph/<string:name>")
api.add_resource(ValveHTTP, "/valve/<string:name>")
api.add_resource(Subscription, "/subscribe/<string:name>")

try:
    # With the reloader enabled, apscheduler executes twice, one in each process
    # We could probably fix this correctly, but just disabling the reloader for now
    app.run(debug=True,host='0.0.0.0', use_reloader=False)
finally:
    print("GPIO Cleanup")
    GPIO.cleanup()

