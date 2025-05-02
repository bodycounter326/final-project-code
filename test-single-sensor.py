# Taken from https://docs.circuitpython.org/projects/vl53l0x/en/latest/examples.html# for testing a single sensor.
import time
import board
import busio
import adafruit_vl53l0x

i2c = busio.I2C(board.SCL, board.SDA)

vl53 = adafruit_vl53l0x.VL53L0X(i2c)


# Main loop will read the range and print it every second.

while True:

    print("Range: {0}mm".format(vl53.range))

    time.sleep(1.0)