"""
FastAGI server using Twisted and StarPy.
"""

import json
import os
import logging
import random
import time
import uuid

from datetime import datetime

import redis
from asterisk.ami import AMIClient, SimpleAction
from uline_redis import ULineRedisManager

from typing import Callable, Generator
from twisted.internet import reactor
from twisted.internet.defer import Deferred, inlineCallbacks
from starpy import fastagi
from starpy.error import AGICommandFailure

from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session

# ---------------- Logging Setup ----------------
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("PBX.FastAGI")
fastagi.log.setLevel(logging.DEBUG)

# ---------- Database Setup ----------
Base = declarative_base()


def mkdir_p(filename: str, base_dir: str = "/var/spool/asterisk/monitor/"):
    """Create the directory for the file if not exists"""
    dir_path = os.path.dirname(filename)
    full_path = os.path.join(base_dir, dir_path)
    os.makedirs(full_path, exist_ok=True)


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

    def is_custom_listed(
        self, list_name: str, caller_id: str, destination: str
    ) -> bool:
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
                {
                    "caller_id": caller_id,
                    "destination": destination,
                    "list_name": list_name,
                },
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

    def get_monitor_filename(self, src: str, dst: str, cdr_uniqueid: str) -> str:
        """Generate a unique monitor filename based on current date + UUIDv4."""
        now = datetime.now()
        date_path = now.strftime("%Y/%m/%d")
        uuid_str = str(uuid.uuid4())
        time_str = now.strftime("%H_%M_%S")
        filename = f"{date_path}/{time_str}_{src}_{dst}"
        with self.get_session() as session:
            # Check if the filename already exists in the database
            existing_filename = session.execute(
                text("""SELECT filename FROM core_monitor_filenames
                        WHERE src = :src AND dst = :dst
                        AND requested_by_api
                        AND not used_by_system order by id limit 1"""),
                {"src": src, "dst": dst},
            ).scalar()
            if existing_filename:
                logger.info(
                    f"Monitor filename already exists for src: {src}, dst: {dst}. Using existing filename: {existing_filename}"
                )
                session.execute(
                    text("""UPDATE core_monitor_filenames
                                SET used_by_system = TRUE, cdr_uniqueid = :cdr_uniqueid
                                WHERE filename = :filename"""),
                    {"filename": existing_filename, "cdr_uniqueid": cdr_uniqueid},
                )
                session.commit()
                return existing_filename
            else:
                session.execute(
                    text(
                        """INSERT INTO core_monitor_filenames (id, src, dst, filename, cdr_uniqueid, used_by_system, created, modified, requested_by_api)
                        VALUES (:id, :src, :dst, :filename, :cdr_uniqueid, :used_by_system, now(), now(), 'f')
                        ON CONFLICT (cdr_uniqueid) DO NOTHING"""
                    ),
                    {
                        "id": uuid_str,
                        "src": src,
                        "dst": dst,
                        "filename": filename,
                        "cdr_uniqueid": cdr_uniqueid,
                        "used_by_system": False,
                    },
                )
                session.commit()
        logger.info(
            f"Generated monitor filename: {filename} for Asterisk Unique ID: {cdr_uniqueid}"
        )
        return filename

    def get_monitor_status(self, caller_id: str, destination: str) -> bool:
        """Get the monitor filename:
        - check the global settings for monitor status,
        - check the Monitor table for a record matching the caller ID and destination
        """

        with self.get_session() as session:
            result = session.execute(
                text("select allow_monitor from core_settings limit 1")
            )
            global_monitor = result.scalar()
            if global_monitor is not True:
                global_monitor = False
            else:
                global_monitor = True

            is_monitor_enabled = session.execute(
                text("""SELECT force_enable_monitor, force_disable_monitor
                        FROM core_monitor
                        WHERE callerid = :caller_id AND destination = :destination LIMIT 1"""),
                {"caller_id": caller_id, "destination": destination},
            )
            row = is_monitor_enabled.fetchone()
            if not row:
                logger.warning(
                    f"No monitor settings found for caller ID: {caller_id}, destination: {destination}"
                )
                return global_monitor

            if row[0] is True:
                logger.info(
                    f"Monitor is force enabled for caller ID: {caller_id}, destination: {destination}"
                )
                return True
            elif row[1] is True:
                logger.info(
                    f"Monitor is force disabled for caller ID: {caller_id}, destination: {destination}"
                )
                return False

            return global_monitor

    def add_callback_record(
        self, src: str, dst: str, service_name: str, delay_seconds: str
    ) -> None:
        """Add a callback record to the database."""
        with self.get_session() as session:
            session.execute(
                text(
                    """INSERT INTO callback_number (src, dst, service_id, schedule_time)
                        VALUES (:src, :dst, (SELECT id FROM callback_service WHERE name = :service_name), now() + interval ':delay_seconds seconds');"""
                ),
                {
                    "src": src,
                    "dst": dst,
                    "service_name": service_name,
                    "delay_seconds": int(delay_seconds),
                },
            )
            session.commit()

    def get_queue_status(self, queue_name: str) -> tuple[int, int]:
        """Get ready members and callers count.
        Primary: Redis cache. Fallback: Direct AMI query.
        Returns: (ready_operators, callers_waiting)
        """
        try:
            state_key = f"asterisk:queue:{queue_name}"
            state = redis_client.get(state_key)
            if state:
                data = json.loads(state)
                members = data.get("members", {})
                calls = data.get("calls", {})

                ready = sum(
                    1
                    for m in members.values()
                    if str(m.get("status")) == "1" and not m.get("paused")
                )

                logger.info(
                    f"Queue {queue_name} from Redis: ready={ready}, callers={len(calls)}"
                )
                return (ready, len(calls))
        except redis.RedisError as e:
            logger.warning(f"Redis unavailable, falling back to AMI: {e}")
        except Exception as e:
            logger.warning(f"Error reading from Redis, falling back to AMI: {e}")

        return self._query_ami_queue_status(queue_name)

    def _query_ami_queue_status(self, queue_name: str) -> tuple[int, int]:
        """Query Asterisk AMI directly for queue status."""
        try:
            ami_host = os.environ.get("AMI_HOST", "127.0.0.1")
            ami_port = int(os.environ.get("AMI_PORT", 5038))
            ami_user = os.environ.get("AMI_USER", "admin")
            ami_pass = os.environ.get("AMI_PASS", "admin")

            client = AMIClient(address=ami_host, port=ami_port, timeout=5)
            future = client.login(username=ami_user, secret=ami_pass)
            if future.response.is_error():
                logger.error("AMI login failed")
                return (0, 0)

            ready = 0
            callers = 0
            events_received = []
            complete_event = False

            def collect_events(event, **kwargs):
                nonlocal complete_event
                events_received.append(event)
                if event.name == "QueueStatusComplete":
                    complete_event = True

            client.add_event_listener(
                on_event=collect_events,
                white_list=["QueueMember", "QueueEntry", "QueueStatusComplete"],
            )

            client.send_action(SimpleAction("QueueStatus", Queue=queue_name))

            start = time.time()
            while time.time() - start < 3 and not complete_event:
                time.sleep(0.1)

            for ev in events_received:
                if ev.name == "QueueMember":
                    if ev.keys.get("Queue") == queue_name:
                        status = ev.keys.get("Status")
                        paused = ev.keys.get("Paused", "0")
                        if status == "1" and paused == "0":
                            ready += 1
                elif ev.name == "QueueEntry":
                    if ev.keys.get("Queue") == queue_name:
                        callers += 1

            client.logoff()
            logger.info(
                f"Queue {queue_name} from AMI: ready={ready}, callers={callers}"
            )
            return (ready, callers)

        except Exception as e:
            logger.error(f"AMI query failed: {e}")
            return (0, 0)


# ---------------- Redis Client ----------------
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)

uline_manager = ULineRedisManager(redis_client=redis_client)


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
        elif network_script == "mixmonitor":
            return self.mixmonitor()
        elif network_script == "add-callback":
            return self.add_callback()
        elif network_script == "queue-status":
            return self.queue_status()
        elif network_script == "parking-uline":
            return self.parking_uline()

        current_time = time.time()
        self.sequence.append(self.agi.sayDateTime, current_time)
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def handle_failure(self, reason) -> None:
        logger.error("AGI error: %s", reason.getTraceback())
        self.agi.finish()

    def add_callback(self) -> Deferred:
        """
        Add a callback record to the database.

        Parameters expected from AGI variables:
        - agi_arg_1: caller_id
        - agi_arg_2: destination
        - agi_arg_3: service_name
        - agi_arg_4: delay_seconds (optional, default 5 seconds)

        :param self: The FastAGIHandler instance.
        :return: A Deferred representing the AGI command sequence.
        :rtype: Deferred
        """

        caller_id = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        destination = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        service_name = self.agi.variables.get(b"agi_arg_3", b"").decode("utf-8")
        delay_seconds = self.agi.variables.get(b"agi_arg_4", b"5").decode("utf-8")

        logger.debug(
            f"Handling ADD CALLBACK Caller ID: {caller_id}, Destination: {destination}, Service Name: {service_name}, Delay Seconds: {delay_seconds}"
        )
        if not caller_id or not destination or not service_name:
            logger.error("Missing parameters for add callback")
            self.sequence.append(self.agi.setVariable, "CALLBACK_ADDED", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        db.add_callback_record(caller_id, destination, service_name, delay_seconds)
        self.sequence.append(self.agi.setVariable, "CALLBACK_ADDED", "1")
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def queue_status(self) -> Deferred:
        """Check queue status: ready operators and waiting callers.
        Sets READYTORECEIVE and QUEUECALLERS channel variables.
        """
        queue_name = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")

        if not queue_name:
            logger.error("No queue name provided for queue-status")
            self.sequence.append(self.agi.setVariable, "READYTORECEIVE", "0")
            self.sequence.append(self.agi.setVariable, "QUEUECALLERS", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        ready, callers = db.get_queue_status(queue_name)
        logger.info(f"Queue {queue_name}: ready={ready}, callers={callers}")

        self.sequence.append(self.agi.setVariable, "READYTORECEIVE", str(ready))
        self.sequence.append(self.agi.setVariable, "QUEUECALLERS", str(callers))
        self.sequence.append(self.agi.finish)
        return self.sequence()

    def mixmonitor(self) -> Deferred:
        """
        Decide whether to start a MixMonitor based on the:
        - AGI variables,
        - parameters,
        - status "Monitor" in the model
        - existence of record in Monitor table
        - allow monitor on the global settings.
        """
        caller_id = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        destination = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        unique_id = self.agi.variables.get(b"agi_uniqueid", b"").decode("utf-8")
        if not caller_id or not destination or not unique_id:
            logger.error("Missing parameters for MixMonitor")
            self.sequence.append(self.agi.setVariable, "MIXMONITOR", "0")
            self.sequence.append(self.agi.finish)
            return self.sequence()

        monitor_status = db.get_monitor_status(caller_id, destination)
        if monitor_status:
            monitor_filename = db.get_monitor_filename(
                caller_id, destination, unique_id
            )  # already inserted to the database
            mkdir_p(
                f"{monitor_filename}.wav"
            )  # Check and create the directory YYYY/MM/DD
            self.sequence.append(self.agi.setVariable, "MIXMONITOR", "1")
            self.sequence.append(
                self.agi.execute, "MIXMONITOR", f"{monitor_filename}.wav", "a"
            )
            self.sequence.append(self.agi.finish)
        else:
            self.sequence.append(self.agi.setVariable, "MIXMONITOR", "0")
            self.sequence.append(self.agi.finish)

        return self.sequence()

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
        self.sequence.append(
            self.agi.setVariable, "BLACKLISTED", "1" if blacklisted else "0"
        )
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
        self.sequence.append(
            self.agi.setVariable, "WHITELISTED", "1" if whitelisted else "0"
        )
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
        self.sequence.append(
            self.agi.setVariable, "CUSTOM_LISTED", "1" if listed else "0"
        )
        self.sequence.append(self.agi.finish)
        return self.sequence()

    @inlineCallbacks
    def parking_uline(self):
        channel = self.agi.variables.get(b"agi_channel", b"?").decode("utf-8")
        caller_id = self.agi.variables.get(b"agi_callerid", b"?").decode("utf-8")

        cdr_uniqueid = (yield self.agi.getVariable("CDR(uniqueid)")) or b""
        if isinstance(cdr_uniqueid, bytes):
            cdr_uniqueid = cdr_uniqueid.decode("utf-8")

        cdr_start = (yield self.agi.getVariable("CDR(start)")) or b""
        if isinstance(cdr_start, bytes):
            cdr_start = cdr_start.decode("utf-8")

        try:
            uline = uline_manager.allocate(
                uniqueid=cdr_uniqueid,
                channel=channel,
                cdr_start=cdr_start,
                caller_id=caller_id,
            )
        except Exception:
            logger.exception("Failed to allocate parking ULINE")
            yield self.agi.setVariable("ULINE", "0")
            yield self.agi.finish()
            return

        if uline is None:
            logger.error("No free parking ULINEs — all slots busy")
            yield self.agi.setVariable("ULINE", "0")
        else:
            yield self.agi.setVariable("ULINE", str(uline))
            logger.info(f"Allocated ULINE={uline} for channel={channel} uniqueid={cdr_uniqueid}")
        yield self.agi.finish()

    def async_sleep(self, seconds: float) -> Deferred:
        """
        Asynchronous sleep function to yield control back to the reactor.
        """
        d = Deferred()
        reactor.callLater(seconds, d.callback, None)
        return d

    @inlineCallbacks
    def dial_with_retry(
        self, peers: list[str], extension: str, max_attempts: int
    ) -> Generator[Deferred, None, None]:
        """
        Dial each peer with the specified extension, retrying up to max_attempts.
        """
        # Shuffle peers randomly at the beginning of each function call
        random.shuffle(peers)

        for attempt in range(1, max_attempts + 1):
            # Select peer sequentially from the shuffled array
            peer_index = (attempt - 1) % len(peers)
            peer = peers[peer_index]
            logger.debug(f"Attempt {attempt}: Dialing {peer}/{extension}")
            yield self.agi.execute("DIAL", f"PJSIP/{extension}@{peer}", "120", "rT")
            try:
                status = yield self.agi.getVariable("DIALSTATUS")
            except AGICommandFailure as err:
                logger.error(f"AGI Command error: {err}")
                yield self.agi.finish()
                return None

            status = status.decode() if isinstance(status, bytes) else status
            logger.info(f"DIALSTATUS = {status}")
            if status == "ANSWER":
                logger.info(
                    f"Successfully dialed {peer}/{extension} on attempt {attempt}"
                )
                yield self.agi.setVariable("TRUNK_GROUP_DIALLED", "1")
                yield self.agi.finish()
                return status
            if status == "BUSY":
                logger.warning(f"Peer {peer} is busy, retrying...")
                yield self.async_sleep(10)  # Wait before retrying
            elif status in ["NOANSWER", "CHANUNAVAIL", "CONGESTION"]:
                logger.warning(f"Peer {peer} returned status {status}, retrying...")
                yield self.async_sleep(1)  # Wait before retrying
            else:
                yield self.async_sleep(2)  # Short wait for unexpected statuses
                logger.error(
                    f"Unexpected DIALSTATUS {status} for peer {peer}, retrying..."
                )
        logger.error(
            f"All attempts to dial trunk group {peers} failed after {max_attempts} attempts"
        )
        yield self.agi.setVariable("TRUNK_GROUP_DIALLED", "0")
        yield self.agi.finish()
        return None

    def dial_trunk_group(self) -> Deferred:
        trunk_group_name = self.agi.variables.get(b"agi_arg_1", b"").decode("utf-8")
        extension = self.agi.variables.get(b"agi_arg_2", b"").decode("utf-8")
        max_attempts = self.agi.variables.get(b"agi_arg_3", b"5").decode("utf-8")
        logger.debug(
            f"Handling DIAL TRUNK GROUP Trunk Group: {trunk_group_name}, Extension: {extension}, Max Attempts: {max_attempts}"
        )
        if not trunk_group_name or not extension:
            logger.error(
                "No trunk group name or extension provided for dial trunk group"
            )
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


# ---------------- Parking ULINE Sweep ----------------
_ULINE_SWEEP_INTERVAL = int(os.environ.get("ULINE_SWEEP_INTERVAL", 300))


def sweep_parking_ulines() -> None:
    """Release stale ULINE slots whose call channel is no longer active."""
    try:
        if not redis_client.exists("asterisk:channels:all"):
            logger.warning("Dashboard not running — skipping ULINE sweep to avoid false positives")
            return

        active_uids = set()
        for key in redis_client.scan_iter("asterisk:uid:*"):
            active_uids.add(key.split(":")[-1])

        uline_keys = list(redis_client.scan_iter("parking:uline:*"))
        if not uline_keys:
            logger.debug("Parking ULINE sweep: no active slots")
            return

        pipe = redis_client.pipeline()
        for key in uline_keys:
            pipe.hgetall(key)
        slot_data = pipe.execute()

        released = 0
        for key, data in zip(uline_keys, slot_data):
            uniqueid = data.get("uniqueid", "")
            if uniqueid and uniqueid not in active_uids:
                redis_client.delete(key, f"parking:uid:{uniqueid}")
                released += 1
                logger.info(f"Sweep released stale {key} (uniqueid={uniqueid})")

        if released:
            logger.info(f"Parking ULINE sweep: released {released} stale slots")
        else:
            logger.debug("Parking ULINE sweep: no stale slots found")
    except Exception as e:
        logger.error(f"Parking ULINE sweep error: {e}")
    finally:
        reactor.callLater(_ULINE_SWEEP_INTERVAL, sweep_parking_ulines)


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
    reactor.callLater(_ULINE_SWEEP_INTERVAL, sweep_parking_ulines)
    reactor.run()


if __name__ == "__main__":
    db = Database()  # Initialize the database connection
    start_fastagi_server()
