import logging
import logging.config
import ssl

from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver

import paho.mqtt.client as mqtt
from docker_secrets import getDocketSecrets

import iotcloud_api
import accessories

# Logging setup
logger = logging.getLogger()
handler = logging.handlers.RotatingFileHandler(
    "../logs/homekit.log", mode="a", maxBytes=1024 * 1024 * 10, backupCount=2
)
formatter = logging.Formatter(
    "%(asctime)s <%(levelname).1s> %(funcName)s:%(lineno)s: %(message)s"
)
logger.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.info("Starting...")

locationId = getDocketSecrets("locationId")

# IotHub api setup
api = iotcloud_api.IotCloudApi(locationId)

# Homekit driver
driver = AccessoryDriver(port=51826, persist_file="/homekit_data/iotcloud.state")
bridge = Bridge(driver, "IotCloud")

# Setup MQTT client
mqttclient = mqtt.Client(client_id="homekit", userdata=bridge, transport="websockets")
token = getDocketSecrets("mqtt_token")
mqttclient.username_pw_set(token, "_")
mqttclient.tls_set(
    ca_certs=None,
    certfile=None,
    keyfile=None,
    cert_reqs=ssl.CERT_REQUIRED,
    tls_version=ssl.PROTOCOL_TLSv1_2,
)


def onSensorUpdated(client, bridge, msg):
    logger.info("Sensor updated")
    bridge.driver.config_changed()


def onLocationUpdated(client, bridge, msg):
    logger.info("Location updated")
    bridge.driver.config_changed()


def onConnect(self, bridge, flags, rc):
    logger.info("MQTT Connected")

    # MQTT constants
    topicHeader = f"v1/{locationId}/+/"
    sensorUpdateTopic = topicHeader + "+/updatedSensor"
    locationUpdatedTopic = f"v1/{locationId}/updatedLocation"

    # Setup subscriptions
    mqttclient.subscribe(locationUpdatedTopic)
    mqttclient.subscribe(sensorUpdateTopic)
    mqttclient.message_callback_add(locationUpdatedTopic, onLocationUpdated)
    mqttclient.message_callback_add(sensorUpdateTopic, onSensorUpdated)

    # Restore the subscriptions
    for acc in bridge.accessories.values():
        acc.subscribe(mqttclient)


mqttclient.on_connect = onConnect

# Connect
mqttclient.connect("mqtt.iotcloud.es", 443, 30)
mqttclient.loop_start()


def setupBridge(bridge, driver):
    devices = api.getDevices()
    for device in devices:
        deviceId = device["deviceId"]
        for sensor in device["sensors"]:
            sensorName = sensor["sensorName"]
            sensorType = sensor["sensorType"]
            sensorId = sensor["sensorId"]
            logger.info(sensorId)
            topic = f"v1/{locationId}/{deviceId}/{sensorId}/"

            if sensorType == "analog":
                if sensorId.endswith("T"):
                    acc = accessories.TempSensor(
                        driver, sensorName, sensorId, mqttclient, topic
                    )
                elif sensorId.endswith("H"):
                    acc = accessories.HumSensor(
                        driver, sensorName, sensorId, mqttclient, topic
                    )
                elif sensorId.endswith("CO2"):
                    acc = accessories.CO2Sensor(
                        driver, sensorName, sensorId, mqttclient, topic
                    )
                else:
                    logger.error(f"Analog sensor {sensorId} not supported")
                    continue

            elif sensorType == "switch":
                acc = accessories.Switch(
                    driver, sensorName, sensorId, mqttclient, topic
                )
            elif sensorType == "led":
                acc = accessories.LedLight(
                    driver, sensorName, sensorId, mqttclient, topic
                )
            elif sensorType == "ledRGB":
                acc = accessories.RGBLight(
                    driver, sensorName, sensorId, mqttclient, topic
                )
            elif sensorType == "thermostat":
                acc = accessories.Thermostat(
                    driver, sensorName, sensorId, mqttclient, topic
                )
            else:
                logger.error(f"Sensor type {sensorType} not supported")
                continue

            bridge.add_accessory(acc)


setupBridge(bridge, driver)
driver.add_accessory(accessory=bridge)
driver.start()
