import logging
import logging.config

import requests
from docker_secrets import getDocketSecrets

logger = logging.getLogger()


class IotCloudApi:

    iotcloudApiUrl = getDocketSecrets("api_url")
    client_id = getDocketSecrets("api_client_id")
    client_secret = getDocketSecrets("api_client_secret")
    auth_url = getDocketSecrets("auth_url")
    audience = getDocketSecrets("api_audience")

    accessToken = ""

    def __init__(self, locationId):
        self.token = ""
        self.locationId = locationId
        self.session = requests.session()

    def getAuthHeader(self):
        return {"Authorization": "Bearer " + self.accessToken}

    def authenticate(self):

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "audience": self.audience,
        }

        result = requests.post(self.auth_url, json=data)

        try:
            decodedResult = result.json()
            self.accessToken = decodedResult["access_token"]
        except (KeyError, TypeError, ValueError):
            logger.error("authenticate: User could NOT be successfully authenticated.")
            return False

        logger.info("authenticate: User authenticated successfully.")
        return True

    def validateResponse(self, response):

        assert response.status_code == 200

        try:
            result = response.json()
        except ValueError:
            logger.warning(
                "validateResponse: the response could not be json decoded. Response: %s"
                % response.text
            )
            raise

        try:
            return result["data"]
        except KeyError:
            return True

    def get(self, url, auth=False):

        headers = self.getAuthHeader() if auth else None

        # First we try to post de data without validating the token,
        # if we get the unauthorized code then we ask for a new token,
        # and if we are not able to get the token after 1 try we abandon
        for numRetries in range(2):
            r = self.session.get(self.iotcloudApiUrl + url, headers=headers, timeout=30)
            if r.status_code != requests.codes.unauthorized:
                break

            # Get the auth token
            authenticationResult = self.authenticate()
            if numRetries == 1 or not authenticationResult:
                return
            # Send again the data with the new token
            headers = self.getAuthHeader()

        return self.validateResponse(r)

    def post(self, url, data, auth=False):

        headers = self.getAuthHeader() if auth else None

        # First we try to post de data without validating the token,
        # if we get the unauthorized code then we ask for a new token,
        # and if we are not able to get the token after 1 try we abandon
        for numRetries in range(2):
            r = self.session.post(
                self.iotcloudApiUrl + url, json=data, headers=headers, timeout=30
            )
            if r.status_code != requests.codes.unauthorized:
                break

            # Get the auth token
            authenticationResult = self.authenticate()
            if numRetries == 1 or not authenticationResult:
                return
            # Send again the data with the new token
            headers = self.getAuthHeader()

        return self.validateResponse(r)

    def getDevices(self):

        locationData = self.get(f"locations/{self.locationId}/devices", auth=True)
        return locationData["devices"]
