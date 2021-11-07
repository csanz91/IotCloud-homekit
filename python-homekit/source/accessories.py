import logging
from colorsys import hsv_to_rgb, rgb_to_hsv

import utils

from pyhap.accessory import Accessory
from pyhap.const import (
    CATEGORY_THERMOSTAT,
    CATEGORY_SENSOR,
    CATEGORY_SWITCH,
    CATEGORY_LIGHTBULB,
)

logger = logging.getLogger()


class IotCloudSensor(Accessory):

    category = CATEGORY_SENSOR

    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):
        super().__init__(driver, sensorName, aid=utils.generateHash(sensorId))

        self.valuesTopic = sensorTopic + "value"
        mqttclient.message_callback_add(self.valuesTopic, self.onValue)

        self.lastValue = 0.0

    def subscribe(self, mqttclient):
        mqttclient.subscribe(self.valuesTopic)

    def onValue(self, client, userdata, msg):
        try:
            # Just remember the latest value
            value = float(msg.payload)
            self.char_sensor.set_value(value)
        except ValueError:
            logger.error(f"The value received: {msg.payload} is not valid")
            value = 0.0

        self.lastValue = value

    def getValue(self):
        return self.lastValue


class HumSensor(IotCloudSensor):
    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):

        super().__init__(driver, sensorName, sensorId, mqttclient, sensorTopic)
        serv = self.add_preload_service("HumiditySensor")
        self.char_sensor = serv.configure_char("CurrentRelativeHumidity")
        self.subscribe(mqttclient)


class TempSensor(IotCloudSensor):
    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):

        super().__init__(driver, sensorName, sensorId, mqttclient, sensorTopic)
        serv = self.add_preload_service("TemperatureSensor")
        self.char_sensor = serv.configure_char("CurrentTemperature")
        self.subscribe(mqttclient)


class CO2Sensor(IotCloudSensor):
    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):

        super().__init__(driver, sensorName, sensorId, mqttclient, sensorTopic)
        serv = self.add_preload_service("CarbonDioxideSensor", ["CarbonDioxideLevel"])
        self.char_sensor = serv.configure_char("CarbonDioxideLevel")
        self.char_CO2_detected = serv.configure_char("CarbonDioxideDetected")
        self.maxCO2Level = 1000.0

        self.subscribe(mqttclient)

    def onValue(self, client, userdata, msg):
        super().onValue(client, userdata, msg)

        self.char_CO2_detected.set_value(self.lastValue > self.maxCO2Level)


class IotCloudLight(Accessory):

    category = CATEGORY_LIGHTBULB

    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):
        super().__init__(driver, sensorName, aid=utils.generateHash(sensorId))

        self.stateTopic = sensorTopic + "state"
        self.setStateTopic = sensorTopic + "setState"
        self.brightnessTopic = sensorTopic + "aux/brightness"
        self.setBrightnessTopic = sensorTopic + "aux/setBrightness"

        self.mqttclient = mqttclient
        mqttclient.message_callback_add(self.stateTopic, self.onState)
        mqttclient.message_callback_add(self.brightnessTopic, self.onBrightness)

    def subscribe(self, mqttclient):
        mqttclient.subscribe(self.stateTopic)
        mqttclient.subscribe(self.brightnessTopic)

    def onState(self, client, userdata, msg):

        try:
            status = utils.decodeBoolean(msg.payload)
        except:
            logger.error(f"The state received: {msg.payload} is not valid")
            return

        self.charOn.set_value(status)

    def onBrightness(self, client, userdata, msg):

        try:
            brightness = float(msg.payload)
        except ValueError:
            logger.error(f"The brightness received: {msg.payload} is not valid")
            return

        self.charBrightness.set_value(int(brightness * 100.0))

    def setState(self, value):
        self.mqttclient.publish(self.setStateTopic, value, qos=2)

    def setBrightness(self, value):
        brightness = value / 100.0
        self.mqttclient.publish(self.setBrightnessTopic, brightness, qos=2)


class LedLight(IotCloudLight):
    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):
        super().__init__(driver, sensorName, sensorId, mqttclient, sensorTopic)

        serv_light = self.add_preload_service("Lightbulb", ["Brightness"])
        self.charOn = serv_light.configure_char("On", setter_callback=self.setState)
        self.charBrightness = serv_light.configure_char(
            "Brightness", setter_callback=self.setBrightness
        )

        self.subscribe(mqttclient)


class RGBLight(IotCloudLight):
    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):
        super().__init__(driver, sensorName, sensorId, mqttclient, sensorTopic)

        serv_light = self.add_preload_service(
            "Lightbulb", ["Brightness", "Hue", "Saturation"]
        )
        self.charOn = serv_light.configure_char("On", setter_callback=self.setState)
        self.charBrightness = serv_light.configure_char(
            "Brightness", setter_callback=self.setBrightness
        )
        self.charHue = serv_light.configure_char("Hue", setter_callback=self.setHue)
        self.charSat = serv_light.configure_char(
            "Saturation", setter_callback=self.setSaturation
        )
        self.saturation = 0.0

        self.colorTopic = sensorTopic + "aux/color"
        self.setColorTopic = sensorTopic + "aux/setColor"

        mqttclient.message_callback_add(self.colorTopic, self.onColor)
        self.subscribe(mqttclient)

    def subscribe(self, mqttclient):
        super().subscribe(mqttclient)
        mqttclient.subscribe(self.colorTopic)

    def onColor(self, client, userdata, msg):

        hexColor = msg.payload

        h, s, v = rgb_to_hsv(
            int(hexColor[2:4], 16), int(hexColor[4:6], 16), int(hexColor[6:8], 16)
        )
        self.charHue.set_value(int(h * 360.0))
        self.charSat.set_value(int(s * 100.0))

    def setSaturation(self, value):
        self.saturation = value / 100.0

    def setHue(self, hue):
        hexColor = "FF%02x%02x%02x" % tuple(
            map(lambda x: int(x * 255), hsv_to_rgb(hue / 360.0, self.saturation, 1.0))
        )
        logger.debug(f"Setting color to {hexColor}")
        self.mqttclient.publish(self.setColorTopic, hexColor, qos=2)


class Switch(Accessory):

    category = CATEGORY_SWITCH

    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):
        super().__init__(driver, sensorName, aid=utils.generateHash(sensorId))

        serv_light = self.add_preload_service("Switch")
        self.char = serv_light.configure_char("On", setter_callback=self.setState)

        self.stateTopic = sensorTopic + "state"
        self.setStateTopic = sensorTopic + "setState"

        self.mqttclient = mqttclient
        mqttclient.message_callback_add(self.stateTopic, self.onState)
        self.subscribe(mqttclient)

    def subscribe(self, mqttclient):
        mqttclient.subscribe(self.stateTopic)

    def onState(self, client, userdata, msg):

        try:
            status = utils.decodeBoolean(msg.payload)
        except:
            logger.error(f"The state received: {msg.payload} is not valid")
            return

        self.char.set_value(status)

    def setState(self, value):
        self.mqttclient.publish(self.setStateTopic, value, qos=2)


class Thermostat(Accessory):

    category = CATEGORY_THERMOSTAT

    def __init__(self, driver, sensorName, sensorId, mqttclient, sensorTopic):
        super().__init__(driver, sensorName, aid=utils.generateHash(sensorId))

        serv = self.add_preload_service("Thermostat", ["CurrentRelativeHumidity"])
        self.charHeatingState = serv.configure_char("CurrentHeatingCoolingState")
        self.charTargetHeatingState = serv.configure_char(
            "TargetHeatingCoolingState", setter_callback=self.setState
        )
        self.charCurrentTemp = serv.configure_char("CurrentTemperature")
        self.charTargetTemp = serv.configure_char(
            "TargetTemperature", setter_callback=self.setSetpoint
        )
        serv.configure_char("TemperatureDisplayUnits", value=0)
        self.charHum = serv.configure_char("CurrentRelativeHumidity")

        self.stateTopic = sensorTopic + "state"
        self.setStateTopic = sensorTopic + "setState"
        self.temperatureTopic = sensorTopic + "value"
        self.humidityTopic = sensorTopic + "aux/humidity"
        self.heatingTopic = sensorTopic + "aux/heating"
        self.setpointTopic = sensorTopic + "aux/setpoint"

        self.mqttclient = mqttclient
        mqttclient.message_callback_add(self.stateTopic, self.onState)
        mqttclient.message_callback_add(self.temperatureTopic, self.onTempValue)
        mqttclient.message_callback_add(self.humidityTopic, self.onHumValue)
        mqttclient.message_callback_add(self.heatingTopic, self.onHeating)
        mqttclient.message_callback_add(self.setpointTopic, self.onSetpointValue)
        self.subscribe(mqttclient)

    def subscribe(self, mqttclient):
        mqttclient.subscribe(self.stateTopic)
        mqttclient.subscribe(self.temperatureTopic)
        mqttclient.subscribe(self.humidityTopic)
        mqttclient.subscribe(self.heatingTopic)
        mqttclient.subscribe(self.setpointTopic)

    def onTempValue(self, client, userdata, msg):
        try:
            # Just remember the latest value
            value = float(msg.payload)
            self.charCurrentTemp.set_value(value)
        except ValueError:
            logger.error(f"The value received: {msg.payload} is not valid")

    def onSetpointValue(self, client, userdata, msg):
        try:
            # Just remember the latest value
            value = float(msg.payload)
            self.charTargetTemp.set_value(value)
        except ValueError:
            logger.error(f"The value received: {msg.payload} is not valid")

    def onHumValue(self, client, userdata, msg):
        try:
            # Just remember the latest value
            value = float(msg.payload)
            self.charHum.set_value(value)
        except ValueError:
            logger.error(f"The value received: {msg.payload} is not valid")

    def setState(self, value):
        newState = value != 0
        self.mqttclient.publish(self.setStateTopic, newState, qos=2)

    def setSetpoint(self, value):
        self.mqttclient.publish(self.setpointTopic, value, qos=2)

    def onState(self, client, userdata, msg):

        try:
            status = utils.decodeBoolean(msg.payload)
        except:
            logger.error(f"The state received: {msg.payload} is not valid")

        mode = 3 if status else 0
        self.charTargetHeatingState.set_value(mode)

    def onHeating(self, client, userdata, msg):

        try:
            status = utils.decodeBoolean(msg.payload)
        except:
            logger.error(f"The state received: {msg.payload} is not valid")

        # 0: off, 1: heating
        self.charHeatingState.set_value(int(status))
