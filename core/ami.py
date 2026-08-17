import logging
import threading
from contextlib import suppress

from asterisk.ami import AMIClient, SimpleAction

from django.conf import settings

logger = logging.getLogger(__name__)


class AsteriskManagementInterface:
    def __init__(self, timeout: int | None = None):
        self.host = settings.ASTERISK_MANAGER_HOST
        self.port = settings.ASTERISK_MANAGER_PORT
        self.username = settings.ASTERISK_MANAGER_USERNAME
        self.password = settings.ASTERISK_MANAGER_SECRET
        if timeout is None:
            timeout = settings.ASTERISK_AMI_DEFAULT_TIMEOUT
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

    def queue_pause(self, *, interface: str, paused: bool, queue: str | None = None):
        """
        Pause or unpause a queue member via AMI QueuePause. Without `queue`
        the pause state applies to the member in every queue it belongs to.
        """
        keys = {"Interface": interface, "Paused": "true" if paused else "false"}
        if queue:
            keys["Queue"] = queue

        action = SimpleAction("QueuePause", **keys)
        logger.debug(action)
        return self.client.send_action(action).response

    def queue_members(self, *, queue: str | None = None, wait_seconds: float | None = None) -> list:
        """
        Return raw QueueMember AMI events for one queue, or every queue when
        `queue` is omitted. Blocks until QueueStatusComplete or `wait_seconds`.
        """
        if wait_seconds is None:
            wait_seconds = settings.ASTERISK_AMI_QUICK_TIMEOUT

        events = []
        complete = threading.Event()

        def collect(event, **kwargs):
            if event.name == "QueueMember":
                events.append(event)
            elif event.name == "QueueStatusComplete":
                complete.set()

        listener = self.client.add_event_listener(
            on_event=collect,
            white_list=["QueueMember", "QueueStatusComplete"],
        )
        try:
            keys = {"Queue": queue} if queue else {}
            action = SimpleAction("QueueStatus", **keys)
            logger.debug(action)
            response = self.client.send_action(action).response
            if response is None:
                raise RuntimeError("AMI QueueStatus timed out.")
            if response.is_error():
                raise RuntimeError(response.keys.get("Message", "QueueStatus failed."))
            complete.wait(wait_seconds)
        finally:
            self.client.remove_event_listener(listener)

        return list(events)

    def logoff(self):
        self.client.logoff()
