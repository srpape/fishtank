#!/usr/bin/env python3

from w1thermsensor import W1ThermSensor
from collections import deque
import numpy

# The number of readings to maintain in the buffer
maintained_readings = 10

# Read the temp sensor
# The temperature reading is unstable
temp_sensor = W1ThermSensor(W1ThermSensor.THERM_SENSOR_DS18B20, "02099177ba76")

# Read some initial values
tempsC = deque([], maxlen=maintained_readings)
for i in range(maintained_readings):
    tempsC.append(temp_sensor.get_temperature(W1ThermSensor.DEGREES_C))

# Main loop
while True:
    tempsC.append(temp_sensor.get_temperature(W1ThermSensor.DEGREES_C))
    tempC = round(numpy.mean(tempsC), 2)
    with open('/tmp/tank_temperature.txt', "w") as f:
        f.write(str(tempC))



