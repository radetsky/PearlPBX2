import logging

from asterisk.ami import AMIClient, SimpleAction

from django.conf import settings

logger = logging.getLogger(__name__)


class AsteriskManagementInterface:
    def __init__(self):
        self.host = settings.ASTERISK_MANAGER_HOST
        self.port = settings.ASTERISK_MANAGER_PORT
        self.username = settings.ASTERISK_MANAGER_USERNAME
        self.password = settings.ASTERISK_MANAGER_SECRET
        self.client = AMIClient(address=self.host, port=self.port, timeout=3600)
        logger.debug("AMI client created. Login...")
        future_response = self.client.login(
            username=self.username, secret=self.password, callback=self._callback_login
        )
        response = future_response.response
        if response.is_error():
            logger.error("AMI client failed to log in.")
            raise Exception("AMI client failed to log in.")

    def _callback_login(self, response):
        logger.debug(response)

    def reload(self):
        self.client.send_action(SimpleAction("Reload"))

    def restart(self):
        command_action = SimpleAction(name="Command", Command="core restart now")
        logger.debug(command_action)
        self.client.send_action(command_action)

    def logoff(self):
        self.client.logoff()
