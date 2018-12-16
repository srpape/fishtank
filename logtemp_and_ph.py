#!/usr/bin/env python3

from urllib.request import urlopen

import urllib.request
import json
import os

with open(os.path.expanduser('~/.fishtank_thingspeak_api_key'), 'r') as f:
    thingspeak_api_key = f.read().rstrip()

baseURL = 'https://api.thingspeak.com/update?api_key=%s' % thingspeak_api_key

def logThingSpeak(temp, pH):
    try:
        f = urlopen(baseURL + "&field1=%s&field2=%s" % (str(temp), str(pH)), timeout=15)
        f.close()
    except Exception:
        # For some reason the data was not accepted
        # ThingSpeek gives a lot of 500 errors
        pass

def logSmartThings(tempF, pH):
    message = {
        'temperatureF': tempF
    }

    myjson = json.dumps(message).encode()

    headers = {
        'CONTENT-TYPE': 'application/json',
        'CONTENT-LENGTH': len(myjson),
        'Device': 'temperature/tank'
    }

    req = urllib.request.Request('http://192.168.1.121:39500/notify', method='NOTIFY', headers=headers, data=myjson)
    urllib.request.urlopen(req, timeout=15)

    # pH Sensor
    if pH is not None:
        message = {
            'pH': pH
        }

        myjson = json.dumps(message).encode()

        headers = {
            'CONTENT-TYPE': 'application/json',
            'CONTENT-LENGTH': len(myjson),
            'Device': 'ph/tank'
        }

        req = urllib.request.Request('http://192.168.1.121:39500/notify', method='NOTIFY', headers=headers, data=myjson)
        urllib.request.urlopen(req, timeout=15)

# Read the temp from our service
with open('/tmp/tank_temperature.txt', 'r') as f:
    tempC = float(f.read())

tempF = round((9.0/5.0 * tempC + 32), 1)

# Read the pH from our service
with open('/tmp/tank_ph.txt', 'r') as f:
    pH = float(f.read())

# Post to ThingSpeak
logThingSpeak(tempF, pH)

# Post to SmartThings
logSmartThings(tempF, pH)

