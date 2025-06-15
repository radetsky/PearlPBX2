"""
FastAGI server using Twisted and StarPy.
"""

import os
import logging
import time
from typing import Callable, Generator
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from starpy import fastagi

from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
import random

# ---------------- Logging Setup ----------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("PBX.FastAGI")
fastagi.log.setLevel(logging.DEBUG)

# ---------- Database Setup ----------
Base = declarative_base()


class Database:
    def __init__(self):
        self.engine = create_engine(self.get_db_url(), echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = scoped_session(sessionmaker(bind=self.engine))

    def get_db_url(self):
        user = os.environ.get("DB_USER", "user")
        password = os.environ.get("DB_PASS", "pass")
        host = os.environ.get("DB_HOST", "localhost")
        port = os.environ.get("DB_PORT", "5432")
        database = os.environ.get("DB_NAME", "postgres")
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    def get_session(self):
        """Returns a new database session."""
        return self.Session()

    def test_connection(self):
        """Test the database connection."""
        try:
            with self.get_session() as session:
                session.execute(text("SELECT 1"))
            logger.info("Database connection successful")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise

    def is_blacklisted(self, caller_id: str, destination: str) -> bool:
        """Check if a caller ID is blacklisted for a specific destination."""

        with self.get_session() as session:
            result = session.execute(
                text(
                    """SELECT 1
                        FROM blacklist
                        WHERE callerid = :caller_id
                        AND (destination = :destination OR destination = '')
                        AND (expiration_date > NOW() OR expiration_date IS NULL)"""
                ),
                {"caller_id": caller_id, "destination": destination},
            )
            return result.scalar() is not None

    def is_whilelisted(self, caller_id: str, destination: str) -> bool:
        """Check if a caller ID is whitelisted for a specific destination."""
        with self.get_session() as session:
            result = session.execute(
                text(
                    """SELECT 1
                        FROM whitelist
                        WHERE callerid = :caller_id
                        AND (destination = :destination OR destination = '')
                        AND (expiration_date > NOW() OR expiration_date IS NULL)"""
                ),
                {"caller_id": caller_id, "destination": destination},
            )
            return result.scalar() is not None

    def is_custom_listed(self, list_name: str, caller_id: str, destination: str) -> bool:
        """Check if a caller ID is listed in a custom list for a specific destination."""
        with self.get_session() as session:
            result = session.execute(
                text(
                    """SELECT 1
                        FROM custom_list_entries cle, custom_lists_names cln
                        WHERE cle.callerid = :caller_id
                        AND (cle.destination = :destination OR cle.destination = '')
                        AND (cle.expiration_date > NOW() OR cle.expiration_date IS NULL)
                        AND cln.id = cle.list_name_id
                        AND cln.name = :list_name"""
                ),
                {"caller_id": caller_id, "destination": destination, "list_name": list_name},
            )
            return result.scalar() is not None

    def get_trunk_group_entries(self, trunk_group_name: str) -> list:
        """Get entries for a specific trunk group."""
        with self.get_session() as session:
            result = session.execute(
                text(
                    """SELECT s.name
                        FROM core_sippeer s
                        JOIN core_trunkgroup_sip_peers tsp ON s.id = tsp.sippeer_id
                        JOIN core_trunkgroup tg ON tg.id = tsp.trunkgroup_id
                        WHERE tg.name = :trunk_group_name;"""
                ),
                {"trunk_group_name": trunk_group_name},
            )
            return [row[0] for row in result.fetchall()]

# ---------------- AGI Handler Class ----------------
class FastAGIHandler:
    def __init__(self, agi: fastagi.FastAGIProtocol):
        self.agi = agi
        self.sequence = fastagi.InSequence()

    def build_sequence(self) -> Deferred:
        logger.debug("Building AGI command sequence")
        network_script = self.agi.variables.get(b"agi_network_script", b"").decode(
            "utf-8"
        )
        logger.debug(f"Network script: {network_script}")
        if network_script == "blacklist":
            return self.blacklist()
        elif network_script == "whitelist":
            return self.whitelist()
        elif network_script == "customlist":
            return self.customlist()
        elif network_script == "dial-trunk-group":
            return self.dial_trunk_group()

        current_time = time.time()
        self.sequence.append(self.agi.sayDateTime, current_time)
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def handle_failure(self, reason) -> None:
        logger.error("AGI error: %s", reason.getTraceback())
        self.agi.finish()

    def blacklist(self) -> Deferred:
        caller_id = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        destination = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        logger.debug(
            f"Handling BLACKLIST Caller ID: {caller_id}, Destination: {destination}"
        )
        if not caller_id:
            logger.error("No caller ID provided for blacklist")
            self.sequence.append(self.agi.setVariable, "BLACKLISTED", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        blacklisted = db.is_blacklisted(caller_id, destination)
        self.sequence.append(self.agi.setVariable, "BLACKLISTED", "1" if blacklisted else "0")
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def whitelist(self) -> Deferred:
        caller_id = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        destination = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        logger.debug(
            f"Handling WHITELIST Caller ID: {caller_id}, Destination: {destination}"
        )
        if not caller_id:
            logger.error("No caller ID provided for whitelist")
            self.sequence.append(self.agi.setVariable, "WHITELISTED", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        whitelisted = db.is_whilelisted(caller_id, destination)
        self.sequence.append(self.agi.setVariable, "WHITELISTED", "1" if whitelisted else "0")
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def customlist(self) -> Deferred:
        list_name = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        caller_id = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        destination = self.agi.variables.get(b"agi_arg_3", b"").decode("utf-8")
        logger.debug(
            f"Handling CUSTOM LIST Caller ID: {caller_id}, Destination: {destination}, List Name: {list_name}"
        )
        if not caller_id or not list_name:
            logger.error("No caller ID or list name provided for custom list")
            self.sequence.append(self.agi.setVariable, "CUSTOM_LISTED", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        listed = db.is_custom_listed(list_name, caller_id, destination)
        self.sequence.append(self.agi.setVariable, "CUSTOM_LISTED", "1" if listed else "0")
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def async_sleep(self, seconds: float) -> Deferred:
        """
        Asynchronous sleep function to yield control back to the reactor.
        """
        d = Deferred()
        reactor.callLater(seconds, d.callback, None)
        return d

    @inlineCallbacks
    def dial_with_retry(self, peers: list[str], extension: str, max_attempts: int) -> Generator[Deferred, None, None]:
        """
        Dial each peer with the specified extension, retrying up to max_attempts.
        """
        for attempt in range(1, max_attempts + 1):
            peer = random.choice(peers)
            logger.debug(f"Attempt {attempt}: Dialing {peer}/{extension}")
            yield self.agi.execute(f"PJSIP/{peer}/{extension}", "120", "rTt")
            status = yield self.agi.getVariable("DIALSTATUS")
            status = status.decode() if isinstance(status, bytes) else status
            logger.info(f"DIALSTATUS = {status}")
            if status == "ANSWER":
                logger.info(f"Successfully dialed {peer}/{extension} on attempt {attempt}")
                self.sequence.append(self.agi.setVariable, "TRUNK_GROUP_DIALLED", "1")
                self.sequence.append(self.agi.finish)
                returnValue(status)
            if status == "BUSY":
                logger.warning(f"Peer {peer} is busy, retrying...")
                yield self.async_sleep(10)  # Wait before retrying
            elif status in ["NOANSWER", "CHANUNAVAIL", "CONGESTION"]:
                logger.warning(f"Peer {peer} returned status {status}, retrying...")
                yield self.async_sleep(5)  # Wait before retrying
            else:
                yield self.async_sleep(2)  # Short wait for unexpected statuses
                logger.error(f"Unexpected DIALSTATUS {status} for peer {peer}, retrying...")
        logger.error(f"All attempts to dial trunk group {peers} failed after {max_attempts} attempts")
        self.sequence.append(self.agi.setVariable, "TRUNK_GROUP_DIALLED", "0")
        self.sequence.append(self.agi.finish)
        returnValue(None)

    def dial_trunk_group(self) -> Deferred:
        trunk_group_name = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        extension = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        max_attempts = self.agi.variables.get(b"agi_arg_3", b"5").decode("utf-8")
        logger.debug(
            f"Handling DIAL TRUNK GROUP Trunk Group: {trunk_group_name}, Extension: {extension}, Max Attempts: {max_attempts}"
        )
        if not trunk_group_name or not extension:
            logger.error("No trunk group name or extension provided for dial trunk group")
            self.sequence.append(self.agi.setVariable, "TRUNK_GROUP_DIALLED", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()
        trunk_group_entries = db.get_trunk_group_entries(trunk_group_name)
        if not trunk_group_entries:
            logger.error(f"No entries found for trunk group: {trunk_group_name}")
            self.sequence.append(self.agi.setVariable, "TRUNK_GROUP_DIALLED", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        return self.dial_with_retry(trunk_group_entries, extension, int(max_attempts))



# ---------------- Main Entry Function ----------------
def agi_entry_function(agi: fastagi.FastAGIProtocol) -> Deferred:
    logger.debug("Received new AGI connection")
    handler = FastAGIHandler(agi)
    db.test_connection()  # Ensure the database connection is valid
    return handler.build_sequence().addErrback(handler.handle_failure)


# ---------------- Server Startup ----------------
def start_fastagi_server(
    host: str = "127.0.0.1",
    port: int = 4573,
    backlog: int = 50,
    handler: Callable[[fastagi.FastAGIProtocol], Deferred] = agi_entry_function,
) -> None:
    """Starts the FastAGI server with the specified parameters."""
    logger.info("Starting FastAGI server")
    factory = fastagi.FastAGIFactory(handler)
    reactor.listenTCP(port, factory, backlog, host)
    logger.info(f"FastAGI server listening on {host}:{port}")
    reactor.run()


if __name__ == "__main__":
    db = Database()  # Initialize the database connection
    start_fastagi_server()
