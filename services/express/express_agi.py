#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Express AGI Service — HTTP Notifier
Reads channel variables set by express_fastagi.py (ULINE, CALLERID, etc.)
and fires an HTTP GET to the Express Taxi API.

Usage in Queue:
    same => n,Queue(express-queue,,,,AGI(express_agi.py))

Or in dialplan:
    same => n,AGI(/path/to/express_agi.py)
"""

import os
import sys
import re
import logging
from typing import Optional, Dict
from urllib.parse import urlencode, urlparse
from pathlib import Path

import requests
from dotenv import load_dotenv

script_dir = Path(__file__).parent
_system_env = Path("/etc/PearlPBX/express/env")
for candidate in (_system_env, script_dir / ".env", script_dir / "env"):
    if candidate.exists():
        load_dotenv(candidate)
        break


class ExpressConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 10))
    DEFAULT_EXPRESS_URL = os.getenv("DEFAULT_EXPRESS_URL", "")
    DEFAULT_EXPRESS_PROVIDER = os.getenv("DEFAULT_EXPRESS_PROVIDER", "")
    DEFAULT_EXPRESS_CLASS = os.getenv("DEFAULT_EXPRESS_CLASS", "0")


class Logger:
    """Logs to stderr — stdout is reserved for the AGI protocol."""

    def __init__(self):
        logging.basicConfig(
            level=getattr(logging, ExpressConfig.LOG_LEVEL),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stderr,
            force=True,
        )
        self.logger = logging.getLogger("ExpressAGI")

    def info(self, msg):  self.logger.info(msg)
    def error(self, msg): self.logger.error(msg)
    def warning(self, msg): self.logger.warning(msg)
    def debug(self, msg): self.logger.debug(msg)


logger = Logger()


# ============ AGI PROTOCOL ============

class AGI:
    """Minimal AGI protocol implementation (stdin/stdout)."""

    def __init__(self):
        self.variables = {}
        self._read_env()

    def _read_env(self):
        while True:
            line = sys.stdin.readline().strip()
            if not line:
                break
            if ": " in line:
                key, value = line.split(": ", 1)
                self.variables[key] = value

    def _send(self, command: str) -> Dict:
        logger.debug(f"AGI >> {command}")
        sys.stdout.write(f"{command}\n")
        sys.stdout.flush()
        response = sys.stdin.readline().strip()
        logger.debug(f"AGI << {response}")

        result = {"code": 0, "result": "", "data": ""}
        if response.startswith("200"):
            result["code"] = 200
            parts = response.split(" ", 2)
            if len(parts) >= 2 and "=" in parts[1]:
                result["result"] = parts[1].split("=", 1)[1]
            if len(parts) >= 3:
                result["data"] = parts[2]
        else:
            parts = response.split(" ", 1)
            try:
                result["code"] = int(parts[0])
            except ValueError:
                pass
            if len(parts) > 1:
                result["data"] = parts[1]
        return result

    def get_variable(self, name: str) -> Optional[str]:
        resp = self._send(f"GET VARIABLE {name}")
        if resp["code"] == 200 and resp["result"] == "1":
            data = resp.get("data", "")
            if data.startswith("(") and data.endswith(")"):
                return data[1:-1]
            return data
        return None

    def set_variable(self, name: str, value: str):
        self._send(f'SET VARIABLE {name} "{value}"')

    def verbose(self, message: str, level: int = 1):
        self._send(f'VERBOSE "{message}" {level}')


# ============ HELPERS ============

def normalize_phone(callerid: str) -> str:
    digits = re.sub(r"\D", "", callerid)
    return digits[-10:] if len(digits) >= 10 else digits


def extract_member_number(member_interface: str) -> str:
    match = re.match(r'^(?:SIP|PJSIP)/(.+)$', member_interface, re.IGNORECASE)
    return match.group(1) if match else member_interface


# ============ HTTP CLIENT ============

def send_to_express(
    server_url: str,
    provider: str,
    caller_id: str,
    member: str,
    uline: int,
    car_class: str,
) -> Dict:
    parsed = urlparse(server_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    params = {
        "provider": provider,
        "from": caller_id,
        "to": member,
        "line": str(uline),
        "carClass": car_class,
    }
    if parsed.query:
        for param in parsed.query.split("&"):
            if "=" in param:
                k, v = param.split("=", 1)
                params.setdefault(k, v)

    full_url = f"{base_url}?{urlencode(params)}"
    logger.info(f"Express HTTP: {full_url}")

    try:
        resp = requests.get(full_url, timeout=ExpressConfig.HTTP_TIMEOUT)
        if resp.status_code == 200:
            logger.info(f"Express OK: {resp.text}")
            return {"success": True}
        else:
            logger.error(f"Express HTTP {resp.status_code}: {resp.text}")
            return {"success": False, "status": resp.status_code}
    except requests.Timeout:
        logger.error(f"Express timeout ({ExpressConfig.HTTP_TIMEOUT}s)")
        return {"success": False, "error": "timeout"}
    except Exception as e:
        logger.error(f"Express HTTP error: {e}")
        return {"success": False, "error": str(e)}


# ============ HANDLERS ============

def handle_incoming_call(agi: AGI):
    logger.info("=" * 50)
    logger.info(f"Incoming: channel={agi.variables.get('agi_channel', '?')}")

    # ULINE was set by express_fastagi.py via FastAGI before this AGI runs
    uline_str = agi.get_variable("ULINE") or "0"
    try:
        uline = int(uline_str)
    except ValueError:
        uline = 0

    if uline == 0:
        logger.error("ULINE not set (FastAGI may have failed) — skipping Express notification")
        agi.verbose("Express: no ULINE, skipping", 1)
        return

    member_interface = agi.get_variable("MEMBERINTERFACE")
    if not member_interface:
        logger.error("MEMBERINTERFACE not set — skipping Express notification")
        agi.verbose("Express: no MEMBERINTERFACE", 1)
        return

    member_number = extract_member_number(member_interface)
    logger.info(f"Member interface: {member_interface}, number: {member_number}")

    callerid_raw = agi.get_variable("CALLERID(num)") or agi.variables.get("agi_callerid", "")
    caller_id = normalize_phone(callerid_raw)

    express_provider = (
        agi.get_variable("YTAXIPROV")
        or agi.get_variable("EXPRESS_PROVIDER")
        or ExpressConfig.DEFAULT_EXPRESS_PROVIDER
    )
    express_class = (
        agi.get_variable("YTAXICLASS")
        or agi.get_variable("EXPRESS_CLASS")
        or ExpressConfig.DEFAULT_EXPRESS_CLASS
    )
    express_url = agi.get_variable("EXPRESS_URL") or ExpressConfig.DEFAULT_EXPRESS_URL

    logger.info(f"ULINE={uline} caller_id={caller_id} member={member_number} provider={express_provider} class={express_class}")

    if not express_url:
        logger.error("EXPRESS_URL not set")
        agi.verbose("Express: no URL configured", 1)
        return

    result = send_to_express(express_url, express_provider, caller_id, member_number, uline, express_class)
    if result.get("success"):
        agi.verbose("Express: OK", 2)
    else:
        agi.verbose(f"Express: error {result.get('error', result.get('status'))}", 1)

    logger.info("Incoming call handler done")


# ============ MAIN ============

def main():
    try:
        agi = AGI()

        action = agi.variables.get("agi_network_script", "") or agi.variables.get("agi_arg_1", "")
        logger.info(f"Express AGI starting, action={action or 'incoming'}")

        handle_incoming_call(agi)

    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
