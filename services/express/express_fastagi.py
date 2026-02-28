#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Express FastAGI Service — ULINE Manager
Allocates a ULINE (Unique Line Number) for each call and stores it in Redis.
Sets the ULINE channel variable so that express_agi.py can read it later.

Endpoints:
  agi://host:4574         - incoming call handler (allocate ULINE, set channel var)
"""

import os
import sys
import logging
import argparse

from twisted.internet import reactor, defer
from twisted.python import log as twisted_log
from starpy import fastagi
from dotenv import load_dotenv

from uline_redis import ULineRedisManager

load_dotenv()


class ExpressConfig:
    """Service configuration from environment variables."""

    FASTAGI_HOST = os.getenv("FASTAGI_HOST", "0.0.0.0")
    FASTAGI_PORT = int(os.getenv("FASTAGI_PORT", 4574))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    ULINE_SWEEP_INTERVAL = int(os.getenv("ULINE_SWEEP_INTERVAL", 300))


def setup_logging():
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, ExpressConfig.LOG_LEVEL),
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    observer = twisted_log.PythonLoggingObserver()
    observer.start()


logger = logging.getLogger("ExpressFastAGI")
uline_manager = ULineRedisManager(ExpressConfig.REDIS_URL)


# ============ AGI HANDLER CLASS ============

class ExpressAGIHandler:
    def __init__(self, agi: fastagi.FastAGIProtocol):
        self.agi = agi

    @defer.inlineCallbacks
    def _get_variable(self, key: str, default: str = "unknown"):
        value = (yield self.agi.getVariable(key)) or default
        return value.decode("utf-8") if isinstance(value, bytes) else value

    @defer.inlineCallbacks
    def handle_incoming(self):
        """Allocate ULINE and set ULINE channel variable."""
        channel = self.agi.variables.get(b"agi_channel", b"?").decode("utf-8")
        caller_id = self.agi.variables.get(b"agi_callerid", b"?").decode("utf-8")

        logger.info("=" * 50)
        logger.info(f"Incoming call: channel={channel}")
        logger.info(f"CallerID: {caller_id}")

        cdr_start = yield self._get_variable("CDR(start)")
        cdr_uniqueid = yield self._get_variable("CDR(uniqueid)")

        logger.info(f"CDR uniqueid: {cdr_uniqueid}")

        uline = uline_manager.allocate(
            uniqueid=cdr_uniqueid,
            channel=channel,
            cdr_start=cdr_start,
            caller_id=caller_id,
            provider="",
        )

        if uline is None:
            logger.error("No free ULINEs — all slots busy")
            yield self.agi.verbose("Express: no free ULINEs", 1)
        else:
            yield self.agi.setVariable("ULINE", str(uline))
            yield self.agi.verbose(f"Express: ULINE={uline}", 2)
            stats = uline_manager.get_stats()
            logger.info(f"ULINE stats: {stats['used']}/{stats['total']} ({stats['usage_percent']}%)")

        logger.info("ULINE allocation done")
        yield self.agi.finish()

    def handle_failure(self, reason) -> None:
        logger.error("AGI error: %s", reason.getTraceback())
        return self.agi.finish()


def agi_entry_function(agi: fastagi.FastAGIProtocol):
    network_script = agi.variables.get(b"agi_network_script", b"").decode("utf-8")
    logger.info(f"Routing: script={network_script!r}")
    handler = ExpressAGIHandler(agi)
    return handler.handle_incoming().addErrback(handler.handle_failure)


# ============ ORPHAN SWEEP ============

def sweep_ulines():
    """
    Periodic sweep: release ULINEs whose call has ended.

    Chain: express:uline:{N} -> uniqueid -> asterisk:uid:{uniqueid}
    If asterisk:uid:{uniqueid} is absent and asterisk:channels:all exists
    (dashboard is running) -> the call is dead -> release ULINE.
    """
    try:
        r = uline_manager.client

        dashboard_alive = r.exists("asterisk:channels:all")
        active_ulines = list(r.scan_iter("express:uline:*"))

        logger.info(
            f"Sweep: {len(active_ulines)} active ULINEs, "
            f"dashboard={'alive' if dashboard_alive else 'DOWN'}"
        )

        if not dashboard_alive:
            if active_ulines:
                logger.warning(
                    "Sweep: dashboard not running — skipping auto-release to avoid false positives"
                )
        else:
            released = 0
            for key in active_ulines:
                data = r.hgetall(key)
                uniqueid = data.get("uniqueid", "")
                channel = data.get("channel", "")
                if not uniqueid:
                    continue

                if r.exists(f"asterisk:uid:{uniqueid}"):
                    continue

                n = key.split(":")[-1]
                logger.warning(
                    f"Sweep: ULINE {n} orphaned "
                    f"(uniqueid={uniqueid}, channel={channel}) — releasing"
                )
                r.delete(key)
                r.delete(f"express:uid:{uniqueid}")
                released += 1

            if released:
                logger.info(f"Sweep: released {released} orphaned ULINE(s)")

    except Exception as e:
        logger.error(f"Sweep error: {e}")
    finally:
        reactor.callLater(ExpressConfig.ULINE_SWEEP_INTERVAL, sweep_ulines)


# ============ MAIN ============

def parse_args():
    parser = argparse.ArgumentParser(description="Express FastAGI Service — ULINE Manager")
    parser.add_argument("--flush-ulines", action="store_true", help="Flush all ULINEs from Redis and exit")
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging()

    if args.flush_ulines:
        count = uline_manager.flush_all()
        print(f"Flushed {count} ULINE keys from Redis")
        sys.exit(0)

    logger.info("=" * 50)
    logger.info("Express FastAGI Service starting (ULINE Manager)")
    logger.info(f"Host: {ExpressConfig.FASTAGI_HOST}:{ExpressConfig.FASTAGI_PORT}")
    logger.info(f"Redis: {ExpressConfig.REDIS_URL}")
    logger.info(f"Sweep interval: {ExpressConfig.ULINE_SWEEP_INTERVAL}s")
    logger.info("=" * 50)

    factory = fastagi.FastAGIFactory(agi_entry_function)
    reactor.listenTCP(ExpressConfig.FASTAGI_PORT, factory, interface=ExpressConfig.FASTAGI_HOST)

    # Start orphan sweep after first interval
    reactor.callLater(ExpressConfig.ULINE_SWEEP_INTERVAL, sweep_ulines)

    logger.info("Waiting for connections from Asterisk...")
    reactor.run()


if __name__ == "__main__":
    main()
