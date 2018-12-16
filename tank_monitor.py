#!/usr/bin/env python3

from AtlasI2C import AtlasI2C
from w1thermsensor import W1ThermSensor
from collections import deque
import numpy

# The number of readings to maintain in the buffer
maintained_readings = 10

# Prepare the temp sensor
temp_sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "02099177ba76")

# Prepare the pH sensor
ph_sensor = AtlasI2C(address=99)

# Read some initial values
temp_readings = deque([], maxlen=maintained_readings)
ph_readings = deque([], maxlen=maintained_readings)

def read_ph(tempC):
    pH = ph_sensor.query('RT,' + str(tempC))
    if pH.startswith('Command succeeded '):
        pH = float(pH[18:].rstrip("\0"))
        return pH
    return None

for i in range(maintained_readings):
    temp_readings.append(temp_sensor.get_temperature(W1ThermSensor.DEGREES_C))
    pH = read_ph(round(numpy.mean(temp_readings), 2))
    if pH is not None:
        ph_readings.append(pH)

# Main loop
while True:
    temp_readings.append(temp_sensor.get_temperature(W1ThermSensor.DEGREES_C))
    tempC = round(numpy.mean(temp_readings), 2)
    with open('/tmp/tank_temperature.txt', "w") as f:
        f.write(str(tempC))

    pH = read_ph(tempC)
    if pH is not None:
        ph_readings.append(pH)
        with open('/tmp/tank_ph.txt', "w") as f:
            f.write(str(round(pH, 2)))

