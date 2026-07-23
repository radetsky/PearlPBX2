import logging
from contextlib import suppress

from asterisk.ami import AMIClient, SimpleAction

from django.conf import settings

logger = logging.getLogger(__name__)


class AsteriskManagementInterface:
    def __init__(self, timeout: int = 3600):
        self.host = settings.ASTERISK_MANAGER_HOST
        self.port = settings.ASTERISK_MANAGER_PORT
        self.username = settings.ASTERISK_MANAGER_USERNAME
        self.password = settings.ASTERISK_MANAGER_SECRET
        self.client = AMIClient(address=self.host, port=self.port, timeout=timeout)
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        with suppress(Exception):
            self.logoff()
        return False

    def reload(self):
        self.client.send_action(SimpleAction("Reload"))

    def soft_reload(self):
        commands = [
            "module reload res_pjsip.so",
            "ael reload",
            "module reload app_queue.so",
            "module reload manager",
            "module reload res_musiconhold.so",
            "module reload app_confbridge.so",
        ]
        for cmd in commands:
            self.client.send_action(SimpleAction(name="Command", Command=cmd))

    def restart(self):
        command_action = SimpleAction(name="Command", Command="core restart now")
        logger.debug(command_action)
        self.client.send_action(command_action)

    def send_originate(
        self,
        *,
        channel: str,
        exten: str,
        context: str,
        priority: int = 1,
        callerid: str | None = None,
        variables: dict | None = None,
        timeout_ms: int = 30000,
        async_originate: bool = False,
    ):
        """
        Send an AMI Originate action and return its future immediately, without
        waiting for the response. Callers that need to originate several legs in
        parallel (e.g. conference parties) should send them all first and only
        then read each future's `.response` — `AMIClient.send_action` writes to
        the socket and returns right away, so nothing here blocks until `.response`
        is accessed.
        """
        keys = {
            "Channel": channel,
            "Exten": exten,
            "Context": context,
            "Priority": priority,
            "Timeout": timeout_ms,
        }
        if callerid:
            keys["CallerID"] = callerid
        if async_originate:
            # With Async, AMI acknowledges the queued request immediately instead of
            # blocking until the call completes.
            keys["Async"] = "true"

        action = SimpleAction("Originate", **keys)
        for name, value in (variables or {}).items():
            action[name] = value

        logger.debug(action)
        return self.client.send_action(action)

    def originate(self, **kwargs):
        return self.send_originate(**kwargs).response

    def logoff(self):
        self.client.logoff()
