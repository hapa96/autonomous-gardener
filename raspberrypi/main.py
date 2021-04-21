import time
import math
import paho.mqtt.client as mqtt
import json
import socket
import tempfile
import sys
from Logger import Logger

from grove.grove_moisture_sensor import GroveMoistureSensor
from grove.gpio import GPIO

S1_IDLE_FREQUENCY = 3600
S1_WATERING_FREQUENCY = 30

logger = Logger(0)

# Define Variables for Raspberry Pi

sensor = GroveMoistureSensor(0)
pump = GPIO(5, GPIO.OUT)

# Watering Flag
pumpWatering = False

BROKER_URL = "mqtt.autonomous-gardener.tech"


def on_connect(client, userdata, flags, rc):
    """
    Called when the broker responds to our connection request.
    client: The client instance for this callback
    userdata: The private user data as set in Client() or user_data_set()
    flags: Response flags sent by the broker
    rc: The connection result
    """
    if rc == 0:
        client.connected_flag = True  # set flag
        logger.log("{} connected".format(client))
    else:
        logger.log("Bad connection Returned code=", rc)


def on_disconnect(client, userdata, rc):
    client.connected_flag = False
    logger.log("Disconnected")


def on_publish(client, userdata, mid):
    logger.log("Publishing message to broker")


def connect_client(client):
    global logger
    """
    Connect a client to the Broker Service and sets all the required tls settings
    """
    client.username_pw_set("fhnw", "iotproject20")
    client.on_connect = on_connect
    client.tls_set()
    logger.log("Connecting to broker " + BROKER_URL)
    client.connect(BROKER_URL, port=443, keepalive=60)


def handle_message(client, userdata, message):
    global logger
    global S1_IDLE_FREQUENCY
    global S1_WATERING_FREQUENCY
    global pumpWatering

    if message.topic == "update-config":
        logger.log("Parsing config")
        new_config = json.loads(message.payload.decode('utf-8'))
        changed = False

        if new_config["sensors"][0]["s1"]["idle_frequency"] != S1_IDLE_FREQUENCY:
            logger.log("Updating idle frequency of S1. New Value: " +
                       str(new_config["sensors"][0]["s1"]["idle_frequency"]))
            S1_IDLE_FREQUENCY = int(
                new_config["sensors"][0]["s1"]
                ["idle_frequency"])
            changed = True

        if new_config["sensors"][0]["s1"]["watering_frequency"] != S1_WATERING_FREQUENCY:
            logger.log(
                "Updating watering frequency of S1. New Value: " +
                str(new_config["sensors"][0]["s1"]["watering_frequency"]))
            S1_WATERING_FREQUENCY = int(new_config["sensors"][0]["s1"][
                "watering_frequency"])
            changed = True

        if changed:
            logger.log("Saving configuration to config.json")
            with open('config/config.json', 'w') as outfile:
                json.dump(new_config, outfile)
        else:
            logger.log("config unchanged")

    else:
        print("New Message from control-hasentrog {}".format(message.payload))
        value = str(message.payload)
        if (value == 'p1-on'):
            pumpWatering = True
            pump.write(1)
            logger.log("turning on pump")

        elif (value == 'p1-off'):
            pumpWatering = False
            pump.write(0)
            logger.log("turning off pump")
        # # MQTT Settings
        # # Publisher


def print_config_load(sensor, val1, val2):
    global logger
    logger.log("Loaded value for " + sensor + " - IDLE: " + str(val1) +
               " / WATERING: " + str(val2))


def set_config_from_file():
    global logger
    global S1_IDLE_FREQUENCY
    global S1_WATERING_FREQUENCY

    logger.log("no connection to servers, loading config from file")
    # Opening JSON file
    f = open('config/config.json',)
    # returns JSON object as
    # a dictionary
    config = json.load(f)

    S1_IDLE_FREQUENCY = int(config["sensors"][0]["s1"]["idle_frequency"])
    S1_WATERING_FREQUENCY = int(
        config["sensors"][0]["s1"]["watering_frequency"])
    print_config_load("S1", S1_IDLE_FREQUENCY, S1_WATERING_FREQUENCY)


def is_connected(hostname):
    try:
        # see if we can resolve the host name -- tells us if there is
        # a DNS listening
        host = socket.gethostbyname(hostname)
        # connect to the host -- tells us if the host is actually
        # reachable
        s = socket.create_connection((host, 80), 2)
        s.close()
        return True
    except:
        pass
    return False


def check_for_dumped_values(broker):
    global logger
    data = {}
    try:
        with open('tmp.json', "r") as json_file:
            data = json.load(json_file)
            if data['measurements']:
                if len(data['measurements']) > 0:
                    logger.log("updating broker")
                    broker.publish("was-offline", json.dumps(data))
                    logger.log("cleaning up tmpfile")
                    init_tmpfile()

    except IOError:
        logger.log("file not found, creating...")
        init_tmpfile()


def main_loop(broker):
    global logger
    global S1_IDLE_FREQUENCY
    global S1_WATERING_FREQUENCY
    global pumpWatering
    last_time = time.time()

    while True:

        next_time = last_time + (S1_IDLE_FREQUENCY
                                 if not pumpWatering else S1_WATERING_FREQUENCY)

        humidity = sensor.moisture
        res = {
            "time": int(round(time.time() * 1000000000)),
            "location": "hasentrog",
            "sensors":
            {"s1": {"moisture": humidity, "pump": pumpWatering}}
        }
        resJSON = json.dumps(res)
        if broker.connected_flag:
            check_for_dumped_values(broker)
            client_publisher.publish("iot-project", resJSON)
        else:
            logger.log("Value: " + str(humidity) + " - saving to file")
            data = {}
            with open('tmp.json', "r") as json_file:
                data = json.load(json_file)
            with open('tmp.json', "w") as json_file:
                data['measurements'].append(res)
                json.dump(data, json_file)
        while(next_time > last_time):
            last_time = time.time()


def init_tmpfile():
    empty_data = {"measurements": []}

    with open('tmp.json', 'w') as outfile:
        json.dump(empty_data, outfile)


if __name__ == "__main__":
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[-1] != "-v"):
        logger.log("Wrong arguments passed")
        sys.exit(2)
    elif len(sys.argv) == 2:
        logger.VERBOSITY = 1

    # Setup MQTT CLIENT
    client_publisher = mqtt.Client(transport="websockets")
    client_publisher.on_disconnect = on_disconnect
    client_publisher.on_publish = on_publish
    client_publisher.connected_flag = False
    client_subscriber = mqtt.Client(transport="websockets")
    client_subscriber.on_message = handle_message
    client_subscriber.on_disconnect = on_disconnect
    client_subscriber.connected_flag = False

    if is_connected(BROKER_URL):

        # Subscribers
        connect_client(client_subscriber)
        client_subscriber.subscribe("update-config")
        client_subscriber.subscribe("control-pump")
        client_subscriber.loop_start()

        connect_client(client_publisher)
        client_publisher.loop_start()

        # safety-pause
        time.sleep(2)

        client_publisher.publish("fetch-config")
    else:
        set_config_from_file()
        logger.log("no connection to servers, saving to file")

    # safety-pause
    time.sleep(2)

    main_loop(client_publisher)
