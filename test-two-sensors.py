# This code is taken from
# https://docs.circuitpython.org/projects/vl53l0x/en/latest/examples.html#multiple-vl53l0x-on-same-i2c-bus
# We used this file for testing the VL53L0X sensors and getting them up and running.

import time
import board
from digitalio import DigitalInOut
from adafruit_vl53l0x import VL53L0X
import busio


i2c = busio.I2C(board.SCL, board.SDA)
# This lock was crutial for getting multiple sensors working,  but is not in the basic setup code. This took quite a while to troubleshoot.
while not i2c.try_lock():
    pass
i2c.unlock()


# declare the digital output pins connected to the "SHDN" pin on each VL53L0X sensor
xshut = [
    DigitalInOut(board.D16),
    DigitalInOut(board.D21),
    # add more VL53L0X sensors by defining their SHDN pins here
]

for power_pin in xshut:
    # make sure these pins are a digital output, not a digital input
    power_pin.switch_to_output(value=False)

vl53 = []

# now change the addresses of the VL53L0X sensors
for i, power_pin in enumerate(xshut):
    print(f"Turning on sensor {i}")
    # turn on the VL53L0X to allow hardware check
    power_pin.value = True
    time.sleep(0.25)
    # instantiate the VL53L0X sensor on the I2C bus & insert it into the "vl53" list
    try:
        sensor = VL53L0X(i2c)
        # vl53.insert(i, sensor)
        # vl53.insert(i, VL53L0X(i2c))  # also performs VL53L0X hardware check

        # no need to change the address of the last VL53L0X sensor
        if i < len(xshut) - 1:
            # default address is 0x29. Change that to something else
            new_addr = 0x30 + i
            print(f"Changing address to {hex(new_addr)}")
            sensor.set_address(new_addr)  # address assigned should NOT be already in use
        vl53.append(sensor)

    except Exception as e:
        print(f"Error initializing sensor {i}: {e}")


def detect_range(count=5):
    """take count=5 samples"""
    while count:
        for index, sensor in enumerate(vl53):
            try:
                print(f"Sensor {index + 1} Range: {(sensor.range) / 1000}m")
            except Exception as e:
                print(f"Error from sensor {index+1}: {e}")
        time.sleep(1.0)
        count -= 1


print(
    "Multiple VL53L0X sensors' addresses are assigned properly\n"
    "execute detect_range() to read each sensors range readings"
)

detect_range(10)
