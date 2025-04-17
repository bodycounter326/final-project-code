import time
import board
import busio
from adafruit_vl53l0x import VL53L0X
import RPi.GPIO as GPIO

# Create I2C bus
print("Program has started!")

# Set XSHUT to BCM 16
GPIO.setmode(GPIO.BCM)
# GPIO.setup(16, GPIO.OUT)
GPIO.setup(20, GPIO.OUT)

# Setup I2C early
i2c = busio.I2C(board.SCL, board.SDA)

# XSHUT sequence
# GPIO.output(16, GPIO.LOW)
GPIO.output(20, GPIO.LOW)
time.sleep(0.1)
# GPIO.output(16, GPIO.HIGH)
GPIO.output(20, GPIO.HIGH)
print("XSHUT reset complete")
time.sleep(0.5)

# Wait for I2C bus to be ready
while not i2c.try_lock():
    pass
print("I2C lock acquired")
i2c.unlock()

# Initiate sensor
vl53 = VL53L0X(i2c)

# Continuous measurement loop
print("Starting distance measurement...")
while True:
    print("Distance: {} m".format((vl53.range) / 1000))
    time.sleep(1)
