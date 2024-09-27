import logging

from asterisk.ami import AMIClient, SimpleAction
from core.models import Settings

logger = logging.getLogger(__name__)


class AsteriskManagementInterface:
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 5038
        self.username = "django"
        self.password = Settings.objects.first().django_manager_secret
        logger.debug(f"django secret: {self.password}")
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
