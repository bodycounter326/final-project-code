import time
import sys
import board
import busio

import threading
import datetime
from digitalio import DigitalInOut
from adafruit_vl53l0x import VL53L0X

import os
from dotenv import load_dotenv
import urllib.parse as up
import psycopg2
#----------------------------------Database connection--------------------------------
load_dotenv()
TIMEZONE = os.getenv("TIMEZONE")
URI = os.getenv("URI")
TABLE = os.getenv("TABLE")
LOG_TABLE = os.getenv("LOG_TABLE") # Table that holds the number of people every hour

#current commands:
EXIT_CMD = f"UPDATE {TABLE} SET current_count = current_count - 1 WHERE id = 1"
ENTER_CMD = f"UPDATE {TABLE} SET current_count = current_count + 1 WHERE id = 1"
GET_COUNT = f"SELECT current_count FROM {TABLE} WHERE id = 1"
RESET_CMD = f"UPDATE {TABLE} SET current_count = 0 WHERE id = 1"
LOG_COUNT = f"INSERT INTO {LOG_TABLE} (datetime, num_people) VALUES (now() AT TIME ZONE '{TIMEZONE}', (SELECT current_count FROM {TABLE} WHERE id = 1))"
DELETE_LOG = f"DELETE FROM {LOG_TABLE} WHERE datetime < now() AT TIME ZONE '{TIMEZONE}' - INTERVAL '5 days')"

TIMEOUT_SECONDS = 3.0
TOLERANCE = 100  # Tolerance for the sensor to be tripped
#

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
    while True:
        curr_time = datetime.datetime.now()
        if  7 <= curr_time.hour <= 21:
            try:
                update_db(DELETE_LOG) # delete entries older than 5 days
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
        #add 1 hr to current time
        next_hour = (curr_time.replace(microsecond=0, second=0, minute=0) +
                     datetime.timedelta(hours=1))
        sleep_seconds = (next_hour - curr_time).total_seconds()

        # Sleep until the next hour
        time.sleep(sleep_seconds)



# --------------------------------Sensor setup----------------------------------
def init_sensors(vl53):
    i2c = busio.I2C(board.SCL, board.SDA)
    while not i2c.try_lock():
        pass
    i2c.unlock()
    # declare the digital output pins connected to the "SHDN" pin on each VL53L0X sensor
    xshut = [
        DigitalInOut(board.D21),
        DigitalInOut(board.D16)
    ]

    for power_pin in xshut:
        # make sure these pins are a digital output, not a digital input
        power_pin.switch_to_output(value=False)

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

def init_baseline(vl53, baseline_distance):
    """Set the baseline distance to the floor for each sensor."""
    for sensor in vl53:
        distances = []
        for i in range(10):
            distances.append(sensor.range)
            time.sleep(0.05)
        avg_distance = sum(distances) / len(distances)
        baseline_distance.append(avg_distance)
        print(f"Sensor {vl53.index(sensor) + 1} baseline distance: {avg_distance / 1000}m")


#----------------------------Detecting range-----------------------------------
def detect_movement():
    # Initialize sensor states
    #1) set_time will hold the timestamp when the sensor detects an object
    #2) reset_time will hold the timestamp when the sensor no longer detects an object
    #3) is_active represents the current state of the sensor... Is it currently in the process of detecting an object?

    sensor_states = [
        {"set_time": None, "reset_time": None, "is_active": False, "last_distance": 0},
        {"set_time": None, "reset_time": None, "is_active": False, "last_distance": 0}
    ]
    #used to prevent the sensor from triggering multiple times...
    last_event_time = time.time()  # Track when we last processed an event
    history_buffer = []  # Track recent sensor activations to help with fast movement

    while True:
        try:
            current_time = time.time()
            distances = [sensor.range for sensor in vl53]

            # Process each sensor's state and and distance
            for i, distance in enumerate(distances):
                sensor_states[i]["last_distance"] = distance

                # Check #1: Inital person detection (object must be a certain height above the base to prevent false positives)
                if distance < baseline_distance[i] - TOLERANCE:
                    # This is the first case of the sensor being triggered, so we set the set_time and set the sensor to "active"
                    if not sensor_states[i]["is_active"]:
                        timestamp = current_time
                        sensor_states[i]["set_time"] = timestamp
                        sensor_states[i]["is_active"] = True
                        print(f"Sensor {i + 1} detected object at {distance / 1000}m")

                        # Add activation to history buffer for fast movement detection
                        history_buffer.append({"sensor": i, "action": "set", "time": timestamp})
                        # Keep history buffer to a reasonable size
                        if len(history_buffer) > 10:
                            history_buffer.pop(0)
                else:
                    # The base distance has been detected... if the sensor is "active", then the person has passed by it.
                    # We then reset the active state and record the "reset_time"
                    if sensor_states[i]["is_active"]:
                        timestamp = current_time
                        sensor_states[i]["reset_time"] = timestamp
                        sensor_states[i]["is_active"] = False
                        print(f"Sensor {i + 1} reset at {timestamp}")

                        # Add reset to history buffer
                        history_buffer.append({"sensor": i, "action": "reset", "time": timestamp})
                        # Keep history buffer to a reasonable size
                        if len(history_buffer) > 10:
                            history_buffer.pop(0)

            # Check #2: Timeout handling
            # Timeout if only one sensor triggered but not the other (a person did not completely enter the gym, or there was something that the sensor dectected that wasnt a person)
            # We must check each sensor state here... Is this the most efficent? I am not sure...
            # If one sensor has reached "reset" and the other has not, and if the time between the current time and when the sensor was "reset" is greater than the timeout period, completely reset the sensor
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

            # Check #3: Person standing under the door (both sensors active for a duration)
            if (sensor_states[0]["is_active"] and sensor_states[1]["is_active"] and
                current_time - max(sensor_states[0]["set_time"], sensor_states[1]["set_time"]) > 1.0):
                if current_time - last_event_time > 2.0:  # Prevent repeated triggers
                    print("Person standing under the door")
                    last_event_time = current_time

            # Check #4: Determining the direction of movement
            # If both sensors have their set and reset times filled...
            if (sensor_states[0]["set_time"] is not None and
                sensor_states[1]["set_time"] is not None and
                sensor_states[0]["reset_time"] is not None and
                sensor_states[1]["reset_time"] is not None):

                # Filter recent history to only the set events
                set_events = [event for event in history_buffer if event["action"] == "set"]

                if len(set_events) >= 2:
                    # Sort by timestamp to ensure proper sequence analysis
                    set_events.sort(key=lambda x: x["time"])

                    # Determine direction based on which sensor was triggered first
                    first_sensor = set_events[0]["sensor"]
                    second_sensor = set_events[1]["sensor"]

                    if first_sensor == 0 and second_sensor == 1:
                        print("Person entering the room")
                        update_db(ENTER_CMD)
                    else:  # first_sensor == 1 and second_sensor == 0
                        print("Person exiting the room")
                        update_db(EXIT_CMD)
                else:
                    # Not enough history data, fall back to traditional comparison
                    if sensor_states[0]["set_time"] < sensor_states[1]["set_time"]:
                        print("Person entering the room")
                        update_db(ENTER_CMD)
                    else:
                        print("Person exiting the room")
                        update_db(EXIT_CMD)

                # Reset all sensor states after processing the event
                for i in range(len(sensor_states)):
                    sensor_states[i]["set_time"] = None
                    sensor_states[i]["reset_time"] = None
                    sensor_states[i]["is_active"] = False

                # Clear history buffer after processing event
                history_buffer = []

                print(f"There are now {get_current_count()} people in the room")
                last_event_time = current_time

            time.sleep(0.01)

        except Exception as e:
            print(f"Error in detect_movement: {e}")


if __name__ == "__main__":
    try:
        print("Setting up sensors...")
        init_sensors(vl53)
        init_baseline(vl53, baseline_distance)
        print("reset database...")
        update_db(RESET_CMD)

        logging_thread = threading.Thread(target=log_count, daemon=True)
        logging_thread.start()

        print("beginning loop...")
        detect_movement()
    except KeyboardInterrupt:
        print("Exiting program.")
    except Exception as e:
        print(f"An error occurred: {e}")
