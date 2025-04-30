# CS326 Final Project: Gym Occupancy Counter
Steps for installing:

1. Clone repo

2. Confirm I2C is enabled: `sudo raspi-config` --> Interfacing Options --> I2C --> Enable --> `sudo reboot`

3. If VL53L0X is connected, (assuming i2c-tools is installed) check using `i2cdetect -y 1`

4. Set up virtual environment `python3 -m venv .venv` and activate `source .venv/bin/activate`

5. Install required packages: `pip3 install -r requirements.txt`

6. Run: `python3 <filename>`

## Project Overview
Our project aims to keep track of how many people are going in and out of the Calvin Gym. We make use of a raspberry pi 4 and two VL53L0X time of flight sensors. These sensors use infrared beams to detect motion. By using two sensors, we can tell which direction a person is walking, and use this to keep track of how many people are currently in the gym. We send these updates to a database hosted in the cloud. This data is also publicly available at [this website](https://morren-fitness-center.azurewebsites.net/).

## Main algorithm
Upon setup, each sensor will have the following attributes: 
1. set_time: this is the first time that the sensor detects motion.
2. reset_time: this is the time that the sensor reaches the baseline distance of detection.
3.  is_active: a boolean that keeps track of if the sensor is currently detecting an object.
4.  last_distance: holds the new distance that the object is detected at.

In an infinite loop, each sensor will be checked for the following conditions:
1. If the sensor has a new detection and the sensor is not active, set the "set_time" and "is_active" attributes. If the new detection is greater than the detection zone, this means the sensor is back to detecting it's baseline value, so the "reset_time" should be set and the "is_active" set to false since the sensor is no longer detecting a object. This was done because the sensors sampling rate could detect a person multiple times as they pass underneath.
2. If only one of the sensors was triggered, reset it after a timeout period.
3. If both sensors are still detecting an object after about 2 seconds, there is probably an object/person under the door.
4. If both the set reset times are set for a sensor, this means the person has passed through the door. We then sort the "set" events based on timestamp, and compare which direction the person came through. We make use of a buffer of sorts to keep track of events that occur. If a person has walked through, the sensors are reset.
5. This loop repeats ever 0.01 seconds.

Upon startup, we have main.py reset the current count to 0, and update the history every hour.
