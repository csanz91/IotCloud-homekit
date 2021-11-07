import logging
import logging.config
import time
import datetime
from dateutil import tz
import hashlib


logger = logging.getLogger()


def decodeBoolean(value):
    value = value.decode()
    assert value.lower() in ["true", "false"]
    state = value.lower() == "true"
    return state


def decodeStatus(value):
    value = value.decode()
    assert value.lower() in ["online", "offline"]
    status = value.lower() == "online"
    return status


def generateHash(deviceId):
    return int(hashlib.sha1(deviceId.encode("utf-8")).hexdigest(), 16) % (10 ** 8)
