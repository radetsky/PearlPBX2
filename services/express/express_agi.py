#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Express AGI Service (Standalone AGI for Queue)
AGI service for Asterisk integration with Express Taxi API
Provides ULINE (Unique Line Number) management for parked calls

This is a standalone AGI script that can be used as Queue member application.
Unlike FastAGI, this script is executed directly by Asterisk for each call.

Usage in Queue:
    same => n,Queue(express-queue,,,,AGI(express_agi.py))

Or in dialplan:
    same => n,AGI(/path/to/express_agi.py)
"""

import os
import sys
import re
import logging
import json
from typing import Optional, Dict
from urllib.parse import urlencode, urlparse
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv


# Load configuration from .env file in the same directory
script_dir = Path(__file__).parent
env_file = script_dir / '.env'
if env_file.exists():
    load_dotenv(env_file)
else:
    # Try 'env' file (without dot)
    env_file = script_dir / 'env'
    if env_file.exists():
        load_dotenv(env_file)


class ExpressConfig:
    """Service configuration"""
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    HTTP_TIMEOUT = int(os.getenv('HTTP_TIMEOUT', 10))

    DEFAULT_EXPRESS_URL = os.getenv('DEFAULT_EXPRESS_URL', '')
    DEFAULT_EXPRESS_PROVIDER = os.getenv('DEFAULT_EXPRESS_PROVIDER', '')
    DEFAULT_EXPRESS_CLASS = os.getenv('DEFAULT_EXPRESS_CLASS', '0')

    # ULINE configuration
    ULINE_MIN = int(os.getenv('ULINE_MIN', 1))
    ULINE_MAX = int(os.getenv('ULINE_MAX', 199))

    # State file for ULINE persistence across AGI calls
    ULINE_STATE_FILE = os.getenv('ULINE_STATE_FILE', '/var/run/express-agi/uline_state.json')


class Logger:
    """Logger wrapper - outputs to stderr for AGI (stdout is reserved for AGI protocol)"""
    def __init__(self):
        self.setup_logging()

    def setup_logging(self):
        """Setup logging to STDERR only (stdout is for AGI protocol)"""
        log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        date_format = '%Y-%m-%d %H:%M:%S'

        logging.basicConfig(
            level=getattr(logging, ExpressConfig.LOG_LEVEL),
            format=log_format,
            datefmt=date_format,
            stream=sys.stderr,
            force=True
        )

        self.logger = logging.getLogger('ExpressAGI')

    def info(self, msg: str):
        self.logger.info(msg)

    def error(self, msg: str):
        self.logger.error(msg)

    def warning(self, msg: str):
        self.logger.warning(msg)

    def debug(self, msg: str):
        self.logger.debug(msg)


logger = Logger()


class ULineManager:
    """
    Manages unique line numbers (ULINE) for calls
    Uses file-based persistence for state across AGI calls
    """

    def __init__(self):
        self.state_file = Path(ExpressConfig.ULINE_STATE_FILE)
        self._ensure_state_dir()

    def _ensure_state_dir(self):
        """Ensure state directory exists"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Fallback to /tmp if we can't create the directory
            self.state_file = Path('/tmp/express-agi-uline_state.json')
            logger.warning(f"Using fallback state file: {self.state_file}")

    def _load_state(self) -> Dict:
        """Load ULINE state from file"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Error loading state file: {e}")
        return {'ulines': {}, 'uniqueid_to_uline': {}}

    def _save_state(self, state: Dict):
        """Save ULINE state to file"""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except IOError as e:
            logger.error(f"Error saving state file: {e}")

    def allocate_uline(self, cdr_start: str, cdr_uniqueid: str, channel: str) -> Optional[int]:
        """
        Allocate a new ULINE for a call
        """
        state = self._load_state()
        ulines = state['ulines']
        uniqueid_to_uline = state['uniqueid_to_uline']

        # Check if this call already has a ULINE
        if cdr_uniqueid in uniqueid_to_uline:
            existing_uline = uniqueid_to_uline[cdr_uniqueid]
            logger.info(f"Call {cdr_uniqueid} already has ULINE {existing_uline}")
            return int(existing_uline)

        # Find available ULINE
        for uline in range(ExpressConfig.ULINE_MIN, ExpressConfig.ULINE_MAX + 1):
            uline_key = str(uline)
            if uline_key not in ulines:
                # Allocate this ULINE
                timestamp = datetime.now().isoformat()
                ulines[uline_key] = {
                    'cdr_start': cdr_start,
                    'cdr_uniqueid': cdr_uniqueid,
                    'channel': channel,
                    'timestamp': timestamp
                }
                uniqueid_to_uline[cdr_uniqueid] = uline_key

                state['ulines'] = ulines
                state['uniqueid_to_uline'] = uniqueid_to_uline
                self._save_state(state)

                logger.info(f"Allocated ULINE {uline} for call {cdr_uniqueid}")
                return uline

        logger.error(f"No available ULINEs! All {ExpressConfig.ULINE_MIN}-{ExpressConfig.ULINE_MAX} are busy")
        return None

    def release_uline(self, cdr_uniqueid: str) -> bool:
        """Release ULINE when call ends"""
        state = self._load_state()
        ulines = state['ulines']
        uniqueid_to_uline = state['uniqueid_to_uline']

        if cdr_uniqueid not in uniqueid_to_uline:
            logger.warning(f"Cannot release ULINE: Call {cdr_uniqueid} not found")
            return False

        uline_key = uniqueid_to_uline[cdr_uniqueid]
        del ulines[uline_key]
        del uniqueid_to_uline[cdr_uniqueid]

        state['ulines'] = ulines
        state['uniqueid_to_uline'] = uniqueid_to_uline
        self._save_state(state)

        logger.info(f"Released ULINE {uline_key} for call {cdr_uniqueid}")
        return True

    def get_stats(self) -> Dict:
        """Get ULINE usage statistics"""
        state = self._load_state()
        total_slots = ExpressConfig.ULINE_MAX - ExpressConfig.ULINE_MIN + 1
        used_slots = len(state['ulines'])
        free_slots = total_slots - used_slots

        return {
            'total': total_slots,
            'used': used_slots,
            'free': free_slots,
            'usage_percent': round((used_slots / total_slots) * 100, 2)
        }


class AGI:
    """Simple AGI protocol implementation"""

    def __init__(self):
        self.variables = {}
        self._read_initial_variables()

    def _read_initial_variables(self):
        """Read AGI environment variables from stdin"""
        while True:
            line = sys.stdin.readline().strip()
            if not line:
                break

            if ': ' in line:
                key, value = line.split(': ', 1)
                self.variables[key] = value
                logger.debug(f"AGI var: {key} = {value}")

    def _send_command(self, command: str) -> Dict:
        """Send AGI command and read response"""
        logger.debug(f"AGI command: {command}")
        sys.stdout.write(f"{command}\n")
        sys.stdout.flush()

        response = sys.stdin.readline().strip()
        logger.debug(f"AGI response: {response}")

        # Parse response: "200 result=<value> [data]"
        result = {'code': 0, 'result': '', 'data': ''}

        if response.startswith('200'):
            result['code'] = 200
            parts = response.split(' ', 2)
            if len(parts) >= 2:
                result_part = parts[1]
                if '=' in result_part:
                    result['result'] = result_part.split('=', 1)[1]
            if len(parts) >= 3:
                result['data'] = parts[2]
        else:
            # Error response
            parts = response.split(' ', 1)
            if parts:
                try:
                    result['code'] = int(parts[0])
                except ValueError:
                    pass
            if len(parts) > 1:
                result['data'] = parts[1]

        return result

    def get_variable(self, name: str) -> Optional[str]:
        """Get channel variable value"""
        response = self._send_command(f'GET VARIABLE {name}')
        if response['code'] == 200 and response['result'] == '1':
            # Value is in parentheses in data field
            data = response.get('data', '')
            if data.startswith('(') and data.endswith(')'):
                return data[1:-1]
            return data
        return None

    def set_variable(self, name: str, value: str):
        """Set channel variable"""
        self._send_command(f'SET VARIABLE {name} "{value}"')

    def verbose(self, message: str, level: int = 1):
        """Send verbose message to Asterisk console"""
        self._send_command(f'VERBOSE "{message}" {level}')

    def noop(self, message: str = ''):
        """NOOP command - does nothing but returns success"""
        if message:
            self._send_command(f'NOOP "{message}"')
        else:
            self._send_command('NOOP')


class AsteriskHelper:
    """Helper methods for Asterisk operations"""

    @staticmethod
    def normalize_phone_number(callerid: str) -> str:
        """Extract last 10 digits from CallerID (Ukrainian format)"""
        digits = re.sub(r'\D', '', callerid)
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    @staticmethod
    def get_peer_ip(agi: AGI, member_interface: str) -> str:
        """Get IP address of peer"""
        if not member_interface:
            return 'unknown'

        try:
            # For PJSIP
            if 'PJSIP' in member_interface.upper():
                result = agi.get_variable('CHANNEL(pjsip,remote_addr)')
                if result:
                    return result.split(':')[0]

            # For SIP
            elif 'SIP' in member_interface.upper():
                result = agi.get_variable('CHANNEL(recvip)')
                if result:
                    return result.split(':')[0]

            # Alternative method
            result = agi.get_variable('SIPCHANINFO(recvip)')
            if result:
                return result.split(':')[0]

        except Exception as e:
            logger.warning(f"Error getting peer IP: {e}")

        return 'unknown'


class ExpressHTTPClient:
    """HTTP client for Express Taxi API"""

    @staticmethod
    def send_incoming_call(
        server_url: str,
        provider: str,
        caller_id: str,
        member_ip: str,
        uline: int,
        car_class: str
    ) -> Dict:
        """Send HTTP request to Express API about incoming call"""
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        params = {
            'provider': provider,
            'from': caller_id,
            'to': member_ip,
            'line': str(uline),
            'carClass': car_class
        }

        # Add existing query params from server_url
        if parsed.query:
            for param in parsed.query.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    if key not in params:
                        params[key] = value

        full_url = f"{base_url}?{urlencode(params)}"

        logger.info(f"Sending request to Express: {full_url}")

        try:
            response = requests.get(full_url, timeout=ExpressConfig.HTTP_TIMEOUT)

            if response.status_code == 200:
                logger.info(f"Express response: {response.text}")
                return {
                    'success': True,
                    'status': response.status_code,
                    'content': response.text
                }
            else:
                logger.error(f"Express HTTP error {response.status_code}: {response.text}")
                return {
                    'success': False,
                    'status': response.status_code,
                    'content': response.text
                }

        except requests.Timeout:
            error_msg = f"Timeout connecting to Express ({ExpressConfig.HTTP_TIMEOUT}s)"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}

        except Exception as e:
            error_msg = f"HTTP request error: {str(e)}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}


def handle_incoming_call(agi: AGI, uline_manager: ULineManager):
    """Main handler for incoming calls (used with Queue)"""
    logger.info("=" * 60)
    logger.info("Express AGI: New request")
    logger.info(f"Channel: {agi.variables.get('agi_channel', 'unknown')}")
    logger.info(f"CallerID: {agi.variables.get('agi_callerid', 'unknown')}")

    # Get CDR information for ULINE
    cdr_start = agi.get_variable('CDR(start)') or 'unknown'
    cdr_uniqueid = agi.get_variable('CDR(uniqueid)') or 'unknown'
    channel = agi.variables.get('agi_channel', '')

    logger.info(f"CDR start: {cdr_start}")
    logger.info(f"CDR uniqueid: {cdr_uniqueid}")

    # Allocate ULINE
    uline = uline_manager.allocate_uline(cdr_start, cdr_uniqueid, channel)

    if uline is None:
        error_msg = "Failed to allocate ULINE - all lines busy"
        logger.error(error_msg)
        agi.verbose(error_msg, 1)
        uline = 0  # Fallback
    else:
        agi.set_variable('ULINE', str(uline))
        agi.verbose(f"Allocated ULINE: {uline}", 2)

        stats = uline_manager.get_stats()
        logger.info(f"ULINE stats: {stats['used']}/{stats['total']} used ({stats['usage_percent']}%)")

    # Read MEMBERINTERFACE
    member_interface = agi.get_variable('MEMBERINTERFACE')
    logger.info(f"MEMBERINTERFACE: {member_interface}")

    # Get operator IP address
    member_ip = AsteriskHelper.get_peer_ip(agi, member_interface)
    logger.info(f"Member IP: {member_ip}")

    # Read and normalize CallerID
    callerid_raw = agi.get_variable('CALLERID(num)') or agi.variables.get('agi_callerid', '')
    caller_id = AsteriskHelper.normalize_phone_number(callerid_raw)
    logger.info(f"CallerID: {callerid_raw} -> {caller_id}")

    # Read EXPRESS_PROVIDER
    express_provider = agi.get_variable('EXPRESS_PROVIDER') or ExpressConfig.DEFAULT_EXPRESS_PROVIDER
    logger.info(f"EXPRESS_PROVIDER: {express_provider}")

    # Read EXPRESS_CLASS
    express_class = agi.get_variable('EXPRESS_CLASS') or ExpressConfig.DEFAULT_EXPRESS_CLASS
    logger.info(f"EXPRESS_CLASS: {express_class}")

    # Read EXPRESS_URL
    express_url = agi.get_variable('EXPRESS_URL') or ExpressConfig.DEFAULT_EXPRESS_URL

    if not express_url:
        error_msg = "EXPRESS_URL not set!"
        logger.error(error_msg)
        agi.verbose(error_msg, 1)
        return

    logger.info(f"EXPRESS_URL: {express_url}")

    # Send HTTP request to Express
    agi.verbose("Sending request to Express...", 2)

    result = ExpressHTTPClient.send_incoming_call(
        express_url,
        express_provider,
        caller_id,
        member_ip,
        uline,
        express_class
    )

    if result.get('success'):
        agi.verbose("Express request successful", 2)
        logger.info("Express request completed successfully")
    else:
        error = result.get('error', result.get('content', 'Unknown error'))
        agi.verbose(f"Express error: {error}", 1)
        logger.error(f"Express request failed: {error}")

    logger.info("Express AGI: Request completed")
    logger.info("=" * 60)


def handle_release(agi: AGI, uline_manager: ULineManager):
    """Handler for releasing ULINE when call ends"""
    logger.info("=" * 60)
    logger.info("Express AGI: ULINE release request")

    cdr_uniqueid = agi.get_variable('CDR(uniqueid)')

    if not cdr_uniqueid:
        error_msg = "CDR(uniqueid) not available"
        logger.error(error_msg)
        agi.verbose(error_msg, 1)
        return

    logger.info(f"CDR uniqueid: {cdr_uniqueid}")

    success = uline_manager.release_uline(cdr_uniqueid)

    if success:
        agi.verbose("ULINE released", 2)
        logger.info("ULINE released successfully")

        stats = uline_manager.get_stats()
        logger.info(f"ULINE stats: {stats['used']}/{stats['total']} used ({stats['usage_percent']}%)")
    else:
        error_msg = "Failed to release ULINE - call not found"
        logger.warning(error_msg)
        agi.verbose(error_msg, 1)

    logger.info("Express AGI: ULINE release completed")
    logger.info("=" * 60)


def main():
    """Main entry point"""
    try:
        agi = AGI()
        uline_manager = ULineManager()

        # Route based on script name (agi_network_script or agi_arg_1)
        script = agi.variables.get('agi_network_script', '')
        arg1 = agi.variables.get('agi_arg_1', '')

        action = script or arg1

        logger.info(f"Express AGI starting, action: {action or 'incoming'}")

        if action == 'release':
            handle_release(agi, uline_manager)
        else:
            # Default: incoming call handler
            handle_incoming_call(agi, uline_manager)

    except Exception as e:
        logger.error(f"Critical error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
