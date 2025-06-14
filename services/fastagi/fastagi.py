"""
Modern FastAGI server using Twisted and StarPy.
"""

import os
import logging
import time
from typing import Callable
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from starpy import fastagi

from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

# ---------------- Logging Setup ----------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("fastagi.modern")
fastagi.log.setLevel(logging.DEBUG)

# ---------- Database Setup ----------
Base = declarative_base()


class Database:
    def __init__(self):
        self.engine = create_engine(self.get_db_url(), echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = scoped_session(sessionmaker(bind=self.engine))

    def get_db_url(self):
        user = os.environ.get("PGUSER", "user")
        password = os.environ.get("PGPASS", "pass")
        host = os.environ.get("PGHOST", "localhost")
        port = os.environ.get("PGPORT", "5432")
        database = os.environ.get("PGBASE", "postgres")
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
