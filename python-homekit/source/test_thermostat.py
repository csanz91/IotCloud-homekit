import logging
import logging.config

import time
import copy

# Logging setup
logger = logging.getLogger()
handler = logging.handlers.RotatingFileHandler(
    "thermostat.log", mode="a", maxBytes=1024 * 1024 * 10, backupCount=2
)
formatter = logging.Formatter(
    "%(asctime)s <%(levelname).1s> %(funcName)s:%(lineno)s: %(message)s"
)
logger.setLevel(logging.INFO)
handler.setFormatter(formatter)
logger.addHandler(handler)


class Thermostat:
    def __init__(self, tags, mqttClient, subscriptionsList):

        # Aux variables
        self.tags = tags
        self.deviceTopicHeader = f"v1/{tags['locationId']}/{tags['deviceId']}/"
        self.topicHeader = self.deviceTopicHeader + tags["sensorId"] + "/"

        # Runtime variables
        self.temperatureReferences = {}
        self.heating = False
        self.setHeatingMem = False
        self.alarm = False
        self.state = False

        # Default settings
        self.startHeatingAt = int(time.time())
        self.setpoint = 0.0
        self.hysteresisHigh = -0.1
        self.hysteresisLow = -0.8
        self.maxHeatingTime = 3600 * 8  # 8 hours
        self.metadata = {}
        self.aux = {}
        self.tempReferenceMem = 0.0
        self.progThermostatShutdownEnabled = False
        self.progThermostatShutdownTime = 0
        self.progThermostatShutdownMem = False
        self.postalCode = None
        self.timeZone = None
        self.pwmTime = 30
        self.pwmActive = False

        self.subscriptionsList = subscriptionsList

        # Subscribe to the relevant topics

    def addTempReference(self, mqttClient, temperatureReferenceTopic, factor):
        if temperatureReferenceTopic not in self.temperatureReferences:
            mqttClient.subscribe(temperatureReferenceTopic)
            self.subscriptionsList.append(temperatureReferenceTopic)
        self.temperatureReferences[temperatureReferenceTopic] = factor

    def updateSettings(self, mqttClient, metadata):
        try:
            self.hysteresisHigh = float(metadata["hysteresisHigh"])
        except:
            pass

        try:
            self.hysteresisLow = float(metadata["hysteresisLow"])
        except:
            pass

        try:
            self.maxHeatingTime = int(metadata["maxHeatingTime"])
        except:
            pass

        try:
            for temperatureReferenceTopic, factor in metadata[
                "temperatureReferences"
            ].items():
                self.addTempReference(mqttClient, temperatureReferenceTopic, factor)
        except:
            logger.error(
                "Excepcion: ", exc_info=True,
            )
            pass

        try:
            self.progThermostatShutdownEnabled = bool(
                metadata["progThermostatShutdownEnabled"]
            )
        except:
            pass

        try:
            self.progThermostatShutdownTime = int(
                metadata["progThermostatShutdownTime"]
            )
        except:
            pass

        self.metadata = copy.deepcopy(metadata)

    def updateAux(self, mqttClient, aux):
        try:
            self.heating = bool(aux["heating"])
        except:
            pass

        try:
            self.setpoint = float(aux["setpoint"])
            logger.debug(f"Received setpoint: {self.setpoint}")
        except:
            pass

        try:
            assert aux["ackAlarm"]
            self.setAlarm(mqttClient, False)
            del aux["ackAlarm"]
        except:
            pass

        self.aux = copy.deepcopy(aux)

    def updatePostalCode(self, postalCode):
        self.postalCode = postalCode

    def updateTimeZone(self, timeZone):
        self.timeZone = timeZone

    def calculateTempReference(self, values):
        tempReference = 0.0
        factorsSum = 0.0
        for temperatureReferenceTopic, factor in self.temperatureReferences.items():
            if not factor:
                continue
            try:
                temperature = values[temperatureReferenceTopic]
                # If the temperature value was received more than 15 minutes ago, discard it
                if temperature.timestamp + 60 * 15 < int(time.time()):
                    logger.warn(
                        "Expired temperature value from the topic: %s"
                        % temperatureReferenceTopic
                    )
                    continue
                factorsSum += factor
                tempReference += temperature.value * factor
            # The sensor was not found
            except (KeyError, TypeError):
                logger.warning(
                    f"Temperature value from the topic:{temperatureReferenceTopic} not available",
                )
        if tempReference and factorsSum:
            tempReference = tempReference / factorsSum

        return tempReference

    def setHeating(self, mqttClient, heating):
        self.setHeatingMem = heating
        print("aux/setHeating")

    def setAlarm(self, mqttClient, alarm):
        self.alarm = alarm
        print("aux/alarm")

    def setState(self, mqttClient, state):
        print("setState")

    def setSetpoint(self, mqttClient, setpoint):
        print("setpoint")

    def engine(self, mqttClient, values):
        print("starting engine")
        # The thermostat cannot run if there is an active alarm or if it is not active
        if self.alarm or not self.state:
            print(
                f"Thermostat: {self.topicHeader} not running because is stopped or an alarm is set",
            )
            # Delete the retentive heating. The device also evaluates this condition
            if self.heating or self.setHeatingMem:
                self.pwmActive = False
                self.setHeating(mqttClient, False)
            return

        tempReference = 20.0
        print(f"{tempReference=}, {self.setpoint=}, {self.heating=}")

        # These values are needed to be able to run the algorithm
        if not tempReference or not self.setpoint:
            logger.warning(
                f"Some of the core values are not valid. tempReference: {tempReference}, setpoint: {self.setpoint}",
            )
            return

        if self.tempReferenceMem != tempReference:
            self.tempReferenceMem = tempReference

        runningTime = int(time.time()) - self.startHeatingAt

        # If the heating has been running for more than [maxHeatingTime] there could be
        # something wrong. Trigger the alarm to protect the instalation.
        if self.heating and runningTime > self.maxHeatingTime:
            print(
                f"Heating running for more than {self.maxHeatingTime} sec. in {self.deviceTopicHeader}. Triggering",
            )
            self.setHeating(mqttClient, False)
            self.setAlarm(mqttClient, True)
            return

        if False:
            # The reference temperature is below the setpoint -> start heating
            if not self.heating and tempReference <= self.setpoint + self.hysteresisLow:
                self.setHeating(mqttClient, True)
                self.startHeatingAt = int(time.time())
                print(f"Start heating for: {self.deviceTopicHeader}",)
            # The reference temperature is above the setpoint -> stop heating
            elif self.heating and tempReference >= self.setpoint + self.hysteresisHigh:
                self.setHeating(mqttClient, False)
                print(f"Stop heating for: {self.deviceTopicHeader}",)

        else:
            # The reference temperature is below the setpoint -> start heating
            if (
                not self.pwmActive
                and tempReference <= self.setpoint + self.hysteresisLow
            ):
                self.startHeatingAt = int(time.time())
                self.pwmActive = True
            # The reference temperature is above the setpoint -> stop heating
            elif (
                self.pwmActive and tempReference >= self.setpoint + self.hysteresisHigh
            ):
                self.pwmActive = False

            # PWM period 10 minutes
            cycleTime = 60
            # Proportional error correction
            pAction = 40.0
            pwnONTime = abs(self.setpoint - tempReference) * pAction
            # Limit ON time between 2 minutes and 6 minutes
            pwnONTime = max(pwnONTime, 12)
            pwnONTime = min(pwnONTime, 36)
            print(pwnONTime)

            pwmON = runningTime % cycleTime < pwnONTime
            print(pwmON)
            print(runningTime)

            if self.pwmActive and not self.heating and pwmON:
                self.setHeating(mqttClient, True)
                print(f"Start heating for: {self.deviceTopicHeader}")
            elif self.heating and (not self.pwmActive or self.pwmActive and not pwmON):
                self.setHeating(mqttClient, False)
                print(f"Stop heating for: {self.deviceTopicHeader}",)
