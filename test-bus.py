import smbus2

bus = smbus2.SMBus(1)
address = 0x29  # Default I2C address for VL53L0X

try:
    bus.write_byte(address, 0x00)  # Write a dummy byte
    print("I2C communication successful!")
except OSError:
    print("I2C communication failed!")
