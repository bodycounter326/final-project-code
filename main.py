import time
import sys
import board
import busio
import os
from dotenv import load_dotenv
# Imports for updating the database every hour
import threading
import datetime

from digitalio import DigitalInOut
from adafruit_vl53l0x import VL53L0X

import urllib.parse as up
import psycopg2

# ----------------------------------Database connection--------------------------------
load_dotenv()
TIMEZONE = os.getenv("TIMEZONE")
URI = os.getenv("URI")
TABLE = os.getenv("TABLE")
LOG_TABLE = os.getenv("LOG_TABLE")  # Table that holds the number of people every hour

# Current commands:
EXIT_CMD = f"UPDATE {TABLE} SET current_count = current_count - 1 WHERE id = 1"
ENTER_CMD = f"UPDATE {TABLE} SET current_count = current_count + 1 WHERE id = 1"
GET_COUNT = f"SELECT current_count FROM {TABLE} WHERE id = 1"
RESET_CMD = f"UPDATE {TABLE} SET current_count = 0 WHERE id = 1"
LOG_COUNT = f"INSERT INTO {LOG_TABLE} (datetime, num_people) VALUES (now() AT TIME ZONE '{TIMEZONE}', (SELECT current_count FROM {TABLE} WHERE id = 1))"
DELETE_LOG = f"DELETE FROM {LOG_TABLE} WHERE datetime < (now() AT TIME ZONE '{TIMEZONE}' - INTERVAL '5 days')"


TIMEOUT_SECONDS = 3.0
# There is a buffer zone of anything shorter than 100mm, the sensor will not trip (this is to add a tolerance to the sensor
# because we compare the previous readings, and the sensor may return slightly different readings over time and could cause a false positive)
TOLERANCE = 100

baseline_distance = []
vl53 = []


def connect_db():
    """Establish and return a connection to the database."""
    up.uses_netloc.append("postgres")
    uri = up.urlparse(URI)
    return psycopg2.connect(
        database=uri.path[1:],
        user=uri.username,
        password=uri.password,
        host=uri.hostname,
        port=uri.port,
        sslmode = 'require'
    )


def update_db(command):
    """Update the database with a given SQL command."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(command)
    conn.commit()
    cursor.close()
    conn.close()


def get_current_count():
    """Retrieve the current count from the database."""
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute(GET_COUNT)
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return result


def log_count():
    """Log the current count to the database on an hourly basis.
    We had help from Github Copilot for figuring out how to deal with logging the count every hour.
    """
    while True:
        curr_time = datetime.datetime.now()
        if 7 <= curr_time.hour <= 21: # Only log between 7am and 9pm, or whenever the gym is (theoretically) open
            try:
                update_db(DELETE_LOG)  # Delete entries older than 5 days here
                count = get_current_count()
                conn = connect_db()
                cursor = conn.cursor()
                cursor.execute(LOG_COUNT, (curr_time, count))
                conn.commit()
                cursor.close()
                conn.close()
                print(f"Logged count: {count} at {curr_time}")
            except Exception as e:
                print(f"Error logging count: {e}")
        # Add 1 hr to the current time
        next_hour = (curr_time.replace(microsecond=0, second=0, minute=0) +
                     datetime.timedelta(hours=1))
        sleep_seconds = (next_hour - curr_time).total_seconds()

        # Sleep until the next hour
        time.sleep(sleep_seconds)


# --------------------------------Sensor setup----------------------------------
def init_sensors(vl53):
    """Initialize the VL53L0X distance sensors.

    This initialization code was taken from
    https://docs.circuitpython.org/projects/vl53l0x/en/latest/examples.html#multiple-vl53l0x-on-same-i2c-bus
    with some minor adjustments made to fit our needs.
    """
    i2c = busio.I2C(board.SCL, board.SDA)
    while not i2c.try_lock():
        pass
    i2c.unlock()
    # Declare the digital output pins connected to the "SHDN" pin on each VL53L0X sensor
    # Switch the BCM pins if you want to change the direction of the sensors are in
    xshut = [
        DigitalInOut(board.D16),
        DigitalInOut(board.D21)
    ]

    for power_pin in xshut:
        # Make sure these pins are a digital output, not a digital input
        power_pin.switch_to_output(value=False)

    # Now change the addresses of the VL53L0X sensors
    for i, power_pin in enumerate(xshut):
        print(f"Turning on sensor {i}")
        # Turn on the VL53L0X to allow hardware check
        power_pin.value = True
        time.sleep(0.25)
        # Instantiate the VL53L0X sensor on the I2C bus & insert it into the "vl53" list
        try:
            sensor = VL53L0X(i2c)
            # vl53.insert(i, sensor)
            # vl53.insert(i, VL53L0X(i2c))  # also performs VL53L0X hardware check
            # No need to change the address of the last VL53L0X sensor(since the other addresses are now unique)
            if i < len(xshut) - 1:
                # Default address is 0x29. Change that to something else
                new_addr = 0x30 + i
                print(f"Changing address to {hex(new_addr)}")
                sensor.set_address(new_addr)
            vl53.append(sensor)

        except Exception as e:
            print(f"Error initializing sensor {i}: {e}")


def init_baseline(vl53, baseline_distance):
    """Set the baseline distance to the floor for each sensor.

    That way we can compare distances between readings to compare if a person has been detected.
    We take 5(arbitrary number, this could probably be lower) readings and average them to get a better baseline reading.
    While the VL53L0X is pretty accurate, there can be some (minor) fluctuations in the readings.
    """
    for sensor in vl53:
        distances = []
        for i in range(5):
            distances.append(sensor.range)
            time.sleep(0.05)
        avg_distance = sum(distances) / len(distances)
        baseline_distance.append(avg_distance)
        print(f"Sensor {vl53.index(sensor) + 1} baseline distance: {avg_distance / 1000}m")


# ----------------------------Detecting range-----------------------------------
def detect_movement():
    """Detect movement through doorway using two distance sensors.

    This function continuously monitors sensors and determines if people are
    entering or exiting based on which sensor triggers first.
    We did have some minor help with Github Copilot for debugging some logic issues.
    """
    # Initialize sensor states
    # 1) set_time will hold the timestamp when the sensor detects an object
    # 2) reset_time will hold the timestamp when the sensor no longer detects an object
    # 3) is_active represents the current state of the sensor... Is it currently in the process of detecting an object?
    # 4) last_distance will hold the "new" detected distance

    sensor_states = [
        {"set_time": None, "reset_time": None, "is_active": False, "last_distance": 0},
        {"set_time": None, "reset_time": None, "is_active": False, "last_distance": 0}
    ]
    # Used to prevent the sensor from triggering multiple times...
    last_event_time = time.time()

    set_events = []  # We make use of a buffer of events, pushing them as states change

    while True:
        try:
            current_time = time.time()

            distances = []
            for sensor in vl53:
                distances.append(sensor.range)

            # Process each sensor's state and and distance
            for i in range(len(distances)):
                distance = distances[i]
                sensor_states[i]["last_distance"] = distance

                # Check #1: See if something is detected. If the distance is less than the buffer zone, there is an object detected
                if distance < baseline_distance[i] - TOLERANCE:
                    # If this IS a new detection, then record the time this sensor is tripped/set, and set it to be "actively" detecting
                    if not sensor_states[i]["is_active"]:
                        timestamp = current_time
                        sensor_states[i]["set_time"] = timestamp
                        sensor_states[i]["is_active"] = True
                        print(f"Sensor {i + 1} detected object at {distance / 1000}m")

                        set_events.append({"sensor": i, "action": "set", "time": timestamp})

                else:
                    # If the distance is greater than the buffer zone and the sensor is "active," this means the person has walked by and reset the sensor
                    if sensor_states[i]["is_active"]:
                        timestamp = current_time
                        sensor_states[i]["reset_time"] = timestamp
                        sensor_states[i]["is_active"] = False
                        print(f"Sensor {i + 1} reset at {timestamp}")

            # Check #2: Timeout handling - check if only one sensor was triggered, just reset it after the timeout period
            if (sensor_states[0]["set_time"] and not sensor_states[1]["set_time"] and
                current_time - sensor_states[0]["set_time"] > TIMEOUT_SECONDS):
                print("Timeout: Only sensor 1 was triggered. Resetting.")
                sensor_states[0]["set_time"] = None
                sensor_states[0]["reset_time"] = None
                sensor_states[0]["is_active"] = False

            if (sensor_states[1]["set_time"] and not sensor_states[0]["set_time"] and
                current_time - sensor_states[1]["set_time"] > TIMEOUT_SECONDS):
                print("Timeout: Only sensor 2 was triggered. Resetting.")
                sensor_states[1]["set_time"] = None
                sensor_states[1]["reset_time"] = None
                sensor_states[1]["is_active"] = False

            # Check #3: Person standing under the door (both sensors active for a longer than 1 second, and prints the person standing under door message every 2 seconds)
            if (sensor_states[0]["is_active"] and sensor_states[1]["is_active"] and
                current_time - max(sensor_states[0]["set_time"], sensor_states[1]["set_time"]) > 1.0):
                if current_time - last_event_time > 2.0:
                    print("Person standing under the door")
                    last_event_time = current_time

            # Check #4: Determining the direction of movement if both sensors have been set/reset
            if (sensor_states[0]["set_time"] is not None and
                sensor_states[1]["set_time"] is not None and
                sensor_states[0]["reset_time"] is not None and
                sensor_states[1]["reset_time"] is not None):

                # We used to sort based on timestamps, but the granularity is not high enough to be accurate for quick movement
                print("sensor", set_events[0]["sensor"], "tripped at", set_events[0]["time"])
                print("sensor", set_events[1]["sensor"], "tripped at", set_events[1]["time"])

                # Thus its better to just check which sensor was appended to the list first.
                first_sensor = set_events[0]["sensor"]
                second_sensor = set_events[1]["sensor"]

                if first_sensor == 0 and second_sensor == 1:
                    print("Person entering the room")
                    update_db(ENTER_CMD)
                else:
                    print("Person exiting the room")
                    update_db(EXIT_CMD)

                # Reset all sensor states after the person/object has passed through
                for i in range(len(sensor_states)):
                    sensor_states[i]["set_time"] = None
                    sensor_states[i]["reset_time"] = None
                    sensor_states[i]["is_active"] = False

                set_events = []

                print(f"There are now {get_current_count()} people in the room")
                last_event_time = current_time

            time.sleep(0.01)

        except Exception as e:
            print(f"Error in detect_movement: {e}")


if __name__ == "__main__":
    try:
        print("Setting up sensors!")
        init_sensors(vl53)
        init_baseline(vl53, baseline_distance)
        print("Starting detection process:")
        detect_movement()

        # This spawns a thread that runs the log_count function every hour, so the Pi stores a snapshot of the current count
        # Commented out for testing

        # logging_thread = threading.Thread(target=log_count, daemon=True)
        # logging_thread.start()

    except KeyboardInterrupt:
        print("Exiting program.")
    except Exception as e:
        print(f"An error occurred: {e}")
