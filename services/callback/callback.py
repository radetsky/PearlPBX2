import json
import logging
import os
import time
import random

import psycopg2
import requests

from asterisk.ami import AMIClient, SimpleAction
from datetime import datetime, timezone
import argparse

class CallbackException(Exception):
    pass

class Callback:
    """Callback Service Class"""
    def __init__(self, **kwargs):
        self.params = kwargs

        self.logger = self.setup_logging()

        self.conn = self.db_connect()
        self.ami = self.ami_connect()
        self.callerids = self.set_callerid()
        self.dbtable = self.params.get("db_table", "callback_callbacknumber")

    def setup_logging(self):
        logger = logging.getLogger("callback")
        loglevel = self.params.get("loglevel", logging.DEBUG)
        logging.basicConfig(level=loglevel, format="%(asctime)s %(levelname)s %(message)s")
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
        except psycopg2.Error as e:
            self.logger.error(f"Database connection error: {e}")
            raise CallbackException("Database connection error")

        return conn

    def ami_connect(self):
        self.logger.debug("Connecting to the asterisk manager interface")
        ami_host = self.params.get("ami_host", "127.0.0.1")
        ami_port = int(self.params.get("ami_port", 5038))
        ami_user = self.params.get("ami_user")
        ami_pass = self.params.get("ami_pass")

        client = AMIClient(address=ami_host, port=ami_port, timeout=3600)
        client.login(username=ami_user, secret=ami_pass)
        client.add_event_listener(
            on_event=self.event_listener,
            on_disconnect=self.on_disconnect,
            white_list=["DialBegin", "DialState", "DialEnd"],
        )
        return client

    def set_callerid(self):
        """ Read the caller IDs from environment variable and return a list """
        callerids = self.params.get("callerids", "")
        return [cid.strip() for cid in callerids.split(",") if cid.strip()]

    def get_callerid(self):

        if not self.callerids:
            return None

        if len(self.callerids) == 1:
            return self.callerids[0]

        return random.choice(self.callerids)

    def on_disconnect(self):
        time.sleep(5)
        self.ami = self.ami_connect()

    def event_listener(self, event, **kwargs):
        self.logger.debug(event)

        if event.name == "DialEnd" and (
            event.keys["DestChannelStateDesc"] == "Down"
            or event.keys["DestChannelStateDesc"] == "Up"
        ):
            status = event.keys["DialStatus"]
            src = event.keys["DestCallerIDNum"]
            dst = event.keys["DestExten"]
            self.logger.info(f"[DialEnd] {src} -> {dst} : {status}")


    def select_first_available(self):
        cursor = self.conn.cursor()

        cursor.execute(
            f"SELECT id, dst, service_name from {self.dbtable} where updated is null order by created limit 1 for update skip locked"
        )
        id_and_dst = cursor.fetchone()
        if id_and_dst is None:
            raise ValueError

        return id_and_dst


    def update_call_status(self, id: int, dst: str, status: str, callerid: str | None):
        dt = datetime.now(timezone.utc)
        cursor = self.conn.cursor()

        cursor.execute(
            f"update {self.dbtable} set updated=%s, src=%s, dial_status=%s where dst=%s and id=%s",
            (dt, callerid, status, dst, id),
        )
        self.conn.commit()

    def call_dst(self, id: int, dst: str, service_name: str):
        self.logger.info(f"Calling to {dst}")
        outbound_context = service_name.replace(" ", "_").lower() if service_name else "callback_outbound"
        answer_context = f"callback-{service_name.replace(' ', '_').lower()}" if service_name else "callback_answer"
        callerid = self.get_callerid()
        kwargs = {
            "ActionID": dst,
            "Channel": f"Local/{dst}@{outbound_context}",
            "Context": answer_context,
            "Exten": dst,
            "Priority": 1,
            "Timeout": 60000,
        }
        if callerid:
            kwargs["Variable"] = f'ORIGCID="{callerid}"'
            kwargs["CallerID"] = callerid

        action = SimpleAction("Originate", **kwargs)
        logging.debug(action)
        resp = self.ami.send_action(action)
        logging.info(resp.response)
        if resp.response.status == "Success":
            self.update_call_status(id, dst, "ANSWER", callerid)
        if resp.response.status == "Error":
            self.update_call_status(id, dst, "BUSY", callerid)

    def process(self):
        """
        Select first available number to call
        Call
        Wait for the answer
        TODO - Webhook
        """

        try:
            (id, dst, service_name) = self.select_first_available()
            self.call_dst(id, dst, service_name)

        except ValueError:
            logging.info("No destinations to call")

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
    parser.add_argument("--db_table", required=False, help="Database table to use for callbacks")
    parser.add_argument("--ami_host", required=False, help="Asterisk Manager Interface host")
    parser.add_argument("--ami_port", type=int, required=False, help="Asterisk Manager Interface port")
    parser.add_argument("--ami_user", required=False, help="Asterisk Manager Interface user")
    parser.add_argument("--ami_pass", required=False, help="Asterisk Manager Interface password")
    parser.add_argument("--callerids", required=False, help="Comma separated list of caller IDs to use")
    parser.add_argument("--process_count", type=int, required=False, help="Number of processes to spawn")
    parser.add_argument("--loglevel", type=int, default=logging.INFO, help="Logging level (default: INFO)")
    parser.add_argument("--dump_config", action="store_true", help="Dump configuration and exit")
    return parser.parse_args()

def read_env_vars(args):
    """Read environment variables and return as a dictionary."""
    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = int(os.getenv("DB_PORT", "5432"))
    db_name = os.getenv("DB_NAME", "callback_db")
    db_user = os.getenv("DB_USER", "callback_user")
    db_pass = os.getenv("DB_PASS", "callback_pass")
    db_table = os.getenv("DB_TABLE", "callback_numbers")
    ami_host = os.getenv("AMI_HOST", "127.0.0.1")
    ami_port = int(os.getenv("AMI_PORT", "5038"))
    ami_user = os.getenv("AMI_USER", "ami_user")
    ami_pass = os.getenv("AMI_PASS", "ami_pass")
    callerids = os.getenv("CALLERIDS", "")
    process_count = int(os.getenv("VA_PROCESS_COUNT", "1"))
    loglevel = int(os.getenv("LOGLEVEL", str(logging.INFO)))

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
        "callerids": callerids,
        "process_count": process_count,
        "loglevel": loglevel,
    }

def merge_args_env(args, env_vars):
    """Merge command line arguments with environment variables.
    Command line arguments take precedence over environment variables.
    """
    merged = {}
    for key in env_vars:
        merged[key] = getattr(args, key) if getattr(args, key) is not None else env_vars[key]
    return merged

def setup_processes(count: int):
    logging.info(f"Setup dedicated processes: {count}")
    i = 0
    while i < count:
        pid = os.fork()
        if pid > 0:
            i = i + 1
            continue
        else:
            break


if __name__ == "__main__":

    args = parse_args()
    env_vars = read_env_vars(args)
    params = merge_args_env(args, env_vars)

    if args.dump_config:
        print(json.dumps(params, indent=4))
        exit(0)

    ps = params.get("process_count", 1)
    if ps is not None and ps > 1:
        setup_processes(ps - 1)  # We also use parent process

    callback = Callback(**params)

    while True:
        try:
            callback.process()

        except (KeyboardInterrupt, SystemExit):
            callback.ami.logoff()
            exit(0)
