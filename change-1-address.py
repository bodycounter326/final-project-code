import time
import board
import busio
from adafruit_vl53l0x import VL53L0X

# Create I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize the sensor with the default address (0x29)
sensor = VL53L0X(i2c)

# Change the address of the sensor (must be a value between 0x08 and 0x77)
new_address = 0x30  # Example new address
print(f"Changing sensor address to {hex(new_address)}...")
sensor.set_address(new_address)

# Verify the new address
print(f"Sensor address changed to {hex(new_address)}!")

# Now you can communicate with the sensor using the new address
while True:
    print(f"Distance: {sensor.range} mm")
    time.sleep(1)
