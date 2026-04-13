import argparse
import json
import logging
import os
import signal
import psycopg2
import sys
import threading
import time

from asterisk.ami import AMIClient, SimpleAction
from datetime import datetime, timezone

DEFAULT_AMI_TIMEOUT = 3600

DIAL_STATUS_ANSWERED = "ANSWERED"
DIAL_STATUS_BUSY = "BUSY"
AMI_DIAL_STATUS_ANSWER = "ANSWER"


class CallbackException(Exception):
    pass


class Callback:
    """Callback Service Class"""

    def __init__(self, **kwargs):
        self.params = kwargs
        self.logger = self.setup_logging()
        self.conn = self.db_connect()
        self.ami = self.ami_connect()
        self.dbtable = self.params.get("db_table", "callback_number")
        self.active_calls_by_dst = {}  # dst -> [(id, context_outbound), ...]
        self.active_calls_by_channel_uid = {}  # channel_uniqueid -> (id, dst)
        self._calls_lock = threading.Lock()
        t = threading.Thread(target=self._health_check_loop, daemon=True)
        t.start()

    def setup_logging(self):
        logger = logging.getLogger("callback")
        loglevel = self.params.get("loglevel", logging.DEBUG)
        logging.basicConfig(
            level=loglevel, format="%(asctime)s %(process)d %(levelname)s %(message)s"
        )
        return logger

    def db_connect(self):
        self.logger.debug("Connecting to the database")
        dbname = self.params.get("db_name")
        dbhost = self.params.get("db_host")
        dbport = self.params.get("db_port")
        dbuser = self.params.get("db_user")
        dbpass = self.params.get("db_pass")

        try:
            conn = psycopg2.connect(
                f"dbname={dbname} user={dbuser} password={dbpass} host={dbhost} port={dbport}"
            )
            conn.autocommit = False  # Enable transaction management
        except psycopg2.Error as e:
            self.logger.error(f"Database connection error: {e}")
            raise CallbackException("Database connection error")

        return conn

    def ensure_db_connected(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            self.conn.rollback()
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            self.logger.warning("DB connection lost, reconnecting...")
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = self.db_connect()

    def ami_connect(self):
        self.logger.debug("Connecting to the asterisk manager interface")
        ami_host = self.params.get("ami_host", "127.0.0.1")
        ami_port = int(self.params.get("ami_port", 5038))
        ami_user = self.params.get("ami_user")
        ami_pass = self.params.get("ami_pass")

        ami_timeout = int(self.params.get("ami_timeout", DEFAULT_AMI_TIMEOUT))
        client = AMIClient(address=ami_host, port=ami_port, timeout=ami_timeout)
        client.login(username=ami_user, secret=ami_pass)
        self.logger.info(f"AMI connected to {ami_host}:{ami_port}")
        client.add_event_listener(
            on_event=self.event_listener,
            white_list=["DialBegin", "DialState", "DialEnd", "Hangup"],
        )
        client.add_listener(
            on_response=lambda source, response: self.logger.debug(
                f"AMI response: status={response.status} keys={response.keys}"
            )
        )
        return client

    def _health_check_loop(self):
        while True:
            time.sleep(30)
            try:
                event = threading.Event()
                self.ami.send_action(SimpleAction("Ping"), lambda _, e=event: e.set())
                if not event.wait(timeout=10):
                    self.logger.error("Health check: no Ping response in 10s, exiting")
                    os._exit(1)
                self.logger.info("Health check: OK")
            except Exception as e:
                self.logger.error(f"Health check failed: {e}, exiting")
                os._exit(1)

    def _pop_from_dst(self, dst: str, call_id: int) -> tuple | None:
        """Remove and return (call_id, context_outbound) by call_id. Caller must hold _calls_lock."""
        entries = self.active_calls_by_dst.get(dst, [])
        for i, entry in enumerate(entries):
            if entry[0] == call_id:
                entries.pop(i)
                if not entries:
                    del self.active_calls_by_dst[dst]
                return entry
        return None

    def _mark_busy(self, id: int, dst: str):
        self.update_call_status(id, dst, DIAL_STATUS_BUSY)
        with self._calls_lock:
            self._pop_from_dst(dst, id)

    def event_listener(self, event, **kwargs):
        self.logger.debug(f"AMI event: {event.name} keys={event.keys}")

        if event.name == "DialBegin":
            dst = event.keys.get("DestExten", "")
            channel_uniqueid = event.keys.get("Uniqueid", "")
            channel = event.keys.get("Channel", "")
            if not channel_uniqueid:
                return
            with self._calls_lock:
                if channel_uniqueid in self.active_calls_by_channel_uid:
                    return  # Already tracking — subsequent retry on the same channel
                entries = self.active_calls_by_dst.get(dst, [])
                for i, (call_id, context_outbound) in enumerate(entries):
                    if channel.startswith(f"Local/{dst}@{context_outbound}"):
                        entries.pop(i)
                        if not entries:
                            del self.active_calls_by_dst[dst]
                        self.active_calls_by_channel_uid[channel_uniqueid] = (
                            call_id,
                            dst,
                        )
                        break

        elif event.name == "DialEnd":
            dial_status = event.keys.get("DialStatus", "")
            channel_uniqueid = event.keys.get("Uniqueid", "")
            if dial_status != AMI_DIAL_STATUS_ANSWER:
                return  # Retry in progress; Hangup will handle final BUSY

            with self._calls_lock:
                entry = self.active_calls_by_channel_uid.pop(channel_uniqueid, None)

            if entry is not None:
                call_id, dst = entry
                src = event.keys.get("DestCallerIDNum", "")
                self.logger.info(f"[DialEnd ANSWERED] {src} -> {dst}")
                try:
                    self.update_call_status(call_id, dst, DIAL_STATUS_ANSWERED)
                except Exception as e:
                    self.logger.error(
                        f"Failed to update status for call {call_id}: {e}"
                    )
                if channel_uniqueid:
                    try:
                        self.update_uniqueid(call_id, channel_uniqueid)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to save uniqueid for call {call_id}: {e}"
                        )

        elif event.name == "Hangup":
            channel_uniqueid = event.keys.get("Uniqueid", "")
            with self._calls_lock:
                entry = self.active_calls_by_channel_uid.pop(channel_uniqueid, None)

            if entry is not None:
                call_id, dst = entry
                self.logger.info(f"[Hangup] {dst}: all retries exhausted, marking BUSY")
                try:
                    self.update_call_status(call_id, dst, DIAL_STATUS_BUSY)
                except Exception as e:
                    self.logger.error(
                        f"Failed to update BUSY status for call {call_id}: {e}"
                    )
                if channel_uniqueid:
                    try:
                        self.update_uniqueid(call_id, channel_uniqueid)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to save uniqueid for call {call_id}: {e}"
                        )

    def select_first_available(self) -> tuple:
        """
        Select the first available callback entry from the database table.
        Locks the selected row to prevent other processes from accessing it.

        Returns:
            tuple: A tuple containing id, dst, service_name, and src of the selected entry.

        Raises:
            ValueError: If no available entry is found.
        """

        self.ensure_db_connected()
        cursor = self.conn.cursor()

        query = """SELECT
                    a.id AS id,
                    a.src AS src,
                    a.dst AS dst,
                    co_out.name AS context_outbound,
                    co_in.name AS context_inbound
                FROM
                    callback_number a
                JOIN
                    callback_service b ON a.service_id = b.id
                JOIN
                    core_routingtable co_out ON b.context_outbound_id = co_out.id
                JOIN
                    dialplan_contexts co_in ON b.context_inbound_id = co_in.id
                WHERE
                    b.is_active = TRUE
                    AND (
                        a.dial_status = 'NEW'
                        OR (a.dial_status = 'PENDING' AND a.updated < NOW() - INTERVAL '10 minutes')
                    )
                    AND a.schedule_time <= NOW()
                ORDER BY
                    a.created
                LIMIT 1
                FOR UPDATE SKIP LOCKED;"""

        cursor.execute(query)
        result = cursor.fetchone()

        if result is None:
            self.conn.rollback()
            raise ValueError("No available callback entry found.")

        update_query = """UPDATE callback_number
               SET dial_status = 'PENDING', updated = NOW()
               WHERE id = %s;"""
        cursor.execute(update_query, (result[0],))
        self.conn.commit()
        return result

    def update_call_status(self, id: int, dst: str, status: str):
        self.ensure_db_connected()
        dt = datetime.now(timezone.utc)
        cursor = self.conn.cursor()

        cursor.execute(
            f"update {self.dbtable} set updated=%s, dial_status=%s where dst=%s and id=%s",
            (dt, status, dst, id),
        )
        self.conn.commit()

    def update_uniqueid(self, id: int, uniqueid: str):
        self.ensure_db_connected()
        cursor = self.conn.cursor()
        cursor.execute(
            f"update {self.dbtable} set uniqueid=%s where id=%s",
            (uniqueid, id),
        )
        self.conn.commit()

    def _on_originate_response(self, id: int, dst: str, response):
        if response.status == "Error":
            self.logger.warning(
                f"AMI Originate {dst}: Error — {response.keys.get('Message', '')}"
            )
            self._mark_busy(id, dst)
        else:
            self.logger.info(f"AMI Originate {dst}: queued")

    def call_dst(
        self, id: int, src: str, dst: str, context_outbound: str, context_inbound: str
    ):
        self.logger.info(f"Calling from {src} to {dst}")

        kwargs = {
            "Channel": f"Local/{dst}@{context_outbound}/n",
            "Context": context_inbound,
            "Exten": dst,
            "Priority": 1,
            "Timeout": 60000,
            "Async": "true",
        }
        if src and src != "":
            kwargs["Variable"] = f'ORIGCID="{src}"'
            kwargs["CallerID"] = src

        with self._calls_lock:
            self.active_calls_by_dst.setdefault(dst, []).append((id, context_outbound))

        action = SimpleAction("Originate", **kwargs)
        self.logger.debug(action)
        try:
            self.ami.send_action(
                action, lambda response: self._on_originate_response(id, dst, response)
            )
        except OSError:
            self._mark_busy(id, dst)
            raise
        except Exception as e:
            self.logger.error(f"AMI send error: {e}")
            self._mark_busy(id, dst)

    def process(self):
        """
        Select first available number to call
        Call
        Wait for the answer
        TODO - Webhook
        """

        try:
            (id, src, dst, context_outbound, context_inbound) = (
                self.select_first_available()
            )
            self.call_dst(id, src, dst, context_outbound, context_inbound)

        except ValueError:
            self.logger.debug("No destinations to call")

        except OSError as e:
            self.logger.critical(f"AMI connection lost, exiting: {e}")
            raise

        except Exception as e:
            self.logger.error(f"Unexpected error in process loop: {e}")

        finally:
            time.sleep(1)


######################### Main #########################


def parse_args():
    """Parse command line arguments.
    CLI Parameters override environment variables.
    """

    parser = argparse.ArgumentParser(description="Callback Service")
    parser.add_argument("--db_host", required=False, help="Database host")
    parser.add_argument("--db_port", type=int, required=False, help="Database port")
    parser.add_argument("--db_name", required=False, help="Database name")
    parser.add_argument("--db_user", required=False, help="Database user")
    parser.add_argument("--db_pass", required=False, help="Database password")
    parser.add_argument(
        "--db_table", required=False, help="Database table to use for callbacks"
    )
    parser.add_argument(
        "--ami_host", required=False, help="Asterisk Manager Interface host"
    )
    parser.add_argument(
        "--ami_port", type=int, required=False, help="Asterisk Manager Interface port"
    )
    parser.add_argument(
        "--ami_user", required=False, help="Asterisk Manager Interface user"
    )
    parser.add_argument(
        "--ami_pass", required=False, help="Asterisk Manager Interface password"
    )
    parser.add_argument(
        "--ami_timeout",
        type=int,
        required=False,
        help="AMI connection timeout in seconds",
    )
    parser.add_argument(
        "--process_count", type=int, required=False, help="Number of processes to spawn"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--dump_config", action="store_true", help="Dump configuration and exit"
    )
    return parser.parse_args()


def read_env_vars(args):
    """Read environment variables and return as a dictionary."""
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "callback_db")
    db_user = os.getenv("DB_USER", "callback_user")
    db_pass = os.getenv("DB_PASS", "callback_pass")
    db_table = os.getenv("DB_TABLE", "callback_number")
    ami_host = os.getenv("AMI_HOST", "127.0.0.1")
    ami_port = int(os.getenv("AMI_PORT", "5038"))
    ami_user = os.getenv("AMI_USER", "ami_user")
    ami_pass = os.getenv("AMI_PASS", "ami_pass")
    ami_timeout = int(os.getenv("AMI_TIMEOUT", str(DEFAULT_AMI_TIMEOUT)))
    process_count = int(os.getenv("VA_PROCESS_COUNT", "1"))

    return {
        "db_host": db_host,
        "db_port": db_port,
        "db_name": db_name,
        "db_user": db_user,
        "db_pass": db_pass,
        "db_table": db_table,
        "ami_host": ami_host,
        "ami_port": ami_port,
        "ami_user": ami_user,
        "ami_pass": ami_pass,
        "ami_timeout": ami_timeout,
        "process_count": process_count,
    }


def merge_args_env(args, env_vars):
    """Merge command line arguments with environment variables.
    Environment variables are used in priority if command line argument is not provided.
    """
    merged = {}
    for key in env_vars:
        merged[key] = env_vars[key] if env_vars[key] is not None else getattr(args, key)
    return merged


def setup_processes(count: int):
    print(f"Setup dedicated processes: {count}")
    i = 0
    while i < count:
        pid = os.fork()
        if pid > 0:
            i = i + 1
            continue
        else:
            break


def handle_signal(signum, frame):
    """Handle signals for graceful shutdown"""
    print(f"Received signal {signum}")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    args = parse_args()
    env_vars = read_env_vars(args)
    params = merge_args_env(args, env_vars)
    params["loglevel"] = logging.DEBUG if args.debug else logging.INFO
    if args.dump_config:
        print(json.dumps(params, indent=4))
        exit(0)

    ps = params.get("process_count", 1)
    if ps is not None and ps > 1:
        print(f"Setting up {ps} processes")
        setup_processes(ps - 1)  # We also use parent process

    callback = Callback(**params)

    while True:
        try:
            callback.process()

        except OSError:
            exit(1)

        except (KeyboardInterrupt, SystemExit):
            try:
                callback.ami.logoff()
            except Exception:
                pass
            exit(0)
