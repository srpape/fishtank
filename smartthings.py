#!/usr/bin/env python3

from flask import Flask
from flask import make_response
from flask import request

from flask_restful import Api, Resource, reqparse

import RPi.GPIO as GPIO
import urllib.request
import json
import numpy

app = Flask(__name__)
api = Api(app)

valves = {
    'drain': {
        'state': 'closed',
        'gpio': 17
    },
    'fill': {
        'state': 'closed',
        'gpio': 27
    }
}

day = 23
night = 25

lights = {
    'tank': {
        'state': '0',
        'states': {
            '0': {
                day: GPIO.LOW,
                night: GPIO.LOW,
            },
            '1': {
                day: GPIO.LOW,
                night: GPIO.HIGH,
            },
            '2': {
                day: GPIO.HIGH,
                night: GPIO.LOW,
            }
        }
    },
}

# Prepare GPIO
GPIO.setmode(GPIO.BCM)
for name, valve in valves.items():
    pin = valve['gpio']
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)


# Load the initial light state (if possible)
try:
    with open('/tmp/tank_light_state.txt', 'r') as f:
        print("Old state: " + lights['tank']['state'])
        lights['tank']['state'] = f.read()
        print("New state: " + lights['tank']['state'])
except IOError:
    pass

for name in lights:
    light = lights[name]
    state = light['states'][light['state']]
    for entry in state:
        GPIO.setup(entry, GPIO.OUT)
        GPIO.output(entry, state[entry])

class Temperature(Resource):
    def get(self, name):
        if(name == "tank"):
            # Read the temp from our service
            with open('/tmp/tank_temperature.txt', 'r') as f:
                tempC = float(f.read())

            tempF = round((9.0/5.0 * tempC + 32), 1)
            message = {
                'temperatureC': tempC,
                'temperatureF': tempF,
            }
            resp = make_response(json.dumps(message))

            resp.headers['CONTENT-TYPE'] = 'application/json'
            resp.headers['Device'] = 'temperature/tank'
            return resp

        return "Temperature sensor not found", 404

class PH(Resource):
    def get(self, name):
        if(name == "tank"):
            # Read the pH from our service
            with open('/tmp/tank_ph.txt', 'r') as f:
                pH = float(f.read())

            message = {
                'pH': pH
            }
            resp = make_response(json.dumps(message))
            resp.headers['Device'] = 'ph/tank'
            return resp

        return "pH sensor not found", 404

class Valve(Resource):
    def get(self, name):
        valve = valves.get(name)
        if not valve:
            return "Valve not found", 404

        message = {
            'state': valve['state']
        }
        resp = make_response(json.dumps(message))
        resp.headers['Device'] = 'valve/' + name
        return resp

    def post(self, name):
        parser = reqparse.RequestParser()
        parser.add_argument("state")
        args = parser.parse_args()

        gpio = None

        state = args['state']
        if state == 'open':
            # Turn off any other valves
            for k, valve in valves.items():
                if k != name and valve['state'] == 'open':
                    print("Disabling " + k)
                    valve['state'] = 'closed'
                    GPIO.output(valve['gpio'], GPIO.LOW)
                    message = {
                        'state': 'closed'
                    }

                    myjson = json.dumps(message).encode()
                    headers = {
                        'CONTENT-TYPE': 'application/json',
                        'CONTENT-LENGTH': len(myjson),
                        'Device': 'valve/' + k
                    }
                    req = urllib.request.Request('http://192.168.1.121:39500/notify', method='NOTIFY', headers=headers, data=myjson)
                    urllib.request.urlopen(req, timeout=15)

            gpio = GPIO.HIGH
        elif state == 'closed':
            gpio = GPIO.LOW
        else:
            return "Invalid State"

        valve = valves.get(name)
        if not valve:
            return "Valve not found", 404

        valve['state'] = state
        GPIO.output(valve['gpio'], gpio)

        message = {
            'state': valve['state']
        }
        resp = make_response(json.dumps(message))
        resp.headers['Device'] = 'valve/' + name
        return resp

class Subscription(Resource):
    def get(self, name):
        return "OK"

class Light(Resource):
    def get(self, name):
        light = lights.get(name)
        if not light:
            return "Light not found", 404

        message = {
            'state': light['state']
        }
        resp = make_response(json.dumps(message))
        resp.headers['Device'] = 'light/tank'
        return resp

    def post(self, name):
        print(request.get_data())

        parser = reqparse.RequestParser()
        parser.add_argument("state")
        args = parser.parse_args()

        light = lights.get(name)
        if not light:
            return "Light not found", 404

        state = args['state']
        if not state in light['states']:
            return "Invalid state", 404

        light['state'] = state

        state = light['states'][light['state']]
        for entry in state:
            GPIO.output(entry, state[entry])

        with open('/tmp/tank_light_state.txt', 'w') as f:
            f.write(str(lights['tank']['state']))

        message = {
            'state': light['state']
        }
        resp = make_response(json.dumps(message))
        resp.headers['Device'] = 'light/tank'
        return resp

api.add_resource(Light, "/light/<string:name>")
api.add_resource(Temperature, "/temperature/<string:name>")
api.add_resource(PH, "/ph/<string:name>")
api.add_resource(Valve, "/valve/<string:name>")
api.add_resource(Subscription, "/subscribe/<string:name>")

try:
    app.run(debug=True,host='0.0.0.0')
finally:
    print("GPIO Cleanup")
    GPIO.cleanup()

