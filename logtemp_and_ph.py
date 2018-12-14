#!/usr/bin/env python3

from urllib.request import urlopen
from w1thermsensor import W1ThermSensor
import urllib.request
import json
from AtlasI2C import AtlasI2C

myAPI = "xxxxxxxxxxxxx"
baseURL = 'https://api.thingspeak.com/update?api_key=%s' % myAPI

def round_of_rating(number):
    return round(number * 10) / 10 

def logThingSpeak(temp, pH):
    try:
        f = urlopen(baseURL + "&field1=%s&field2=%s" % (str(temp), str(pH)), timeout=15)
        f.close()
    except Exception:
        # For some reason the data was not accepted
        # ThingSpeek gives a lot of 500 errors 
        pass

def logSmartThings(temp, pH = None):
    message = {
        'temperature': tempF
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

# Read the temp sensor
sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "02099177ba76")
tempC = round_of_rating(sensor.get_temperature(W1ThermSensor.DEGREES_C))
tempF = round(9.0/5.0 * tempC + 32, 3)

# Read the pH sensor
ph_sensor = AtlasI2C(address=99)

pH = ph_sensor.query('RT,' + str(tempC))
if pH.startswith('Command succeeded '):
    pH = round(float(pH[18:].rstrip("\0")), 2)

# Post to ThingSpeak
logThingSpeak(tempF, pH)

# Post to SmartThings
logSmartThings(tempF, pH)

