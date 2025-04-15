import time
import board
import busio
from adafruit_vl53l0x import VL53L0X

# Create I2C bus
print("Program has started!")
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize the sensor
vl53 = VL53L0X(i2c)

# Continuous measurement loop
print("Starting distance measurement...")
while True:
    print("Distance: {} mm".format(vl53.range))
    time.sleep(1)
