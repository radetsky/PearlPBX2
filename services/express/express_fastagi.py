#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Express FastAGI Service
FastAGI service for Asterisk integration with Express Taxi API
Provides ULINE (Unique Line Number) management for parked calls
"""

import os
import sys
import re
import logging
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode, urlparse
from datetime import datetime

from twisted.internet import reactor, defer
from twisted.python import log as twisted_log
from starpy import fastagi
import aiohttp
import asyncio
from dotenv import load_dotenv


# Load configuration
load_dotenv()


class ExpressConfig:
    """Service configuration"""

    FASTAGI_HOST = os.getenv("FASTAGI_HOST", "0.0.0.0")
    FASTAGI_PORT = int(os.getenv("FASTAGI_PORT", 4574))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", 10))

    DEFAULT_EXPRESS_URL = os.getenv("DEFAULT_EXPRESS_URL", "")
    DEFAULT_EXPRESS_PROVIDER = os.getenv("DEFAULT_EXPRESS_PROVIDER", "")
    DEFAULT_EXPRESS_CLASS = os.getenv("DEFAULT_EXPRESS_CLASS", "0")

    # ULINE configuration
    ULINE_MIN = int(os.getenv("ULINE_MIN", 1))
    ULINE_MAX = int(os.getenv("ULINE_MAX", 199))


class Logger:
    """Logger wrapper - all output to STDOUT for systemd/journalctl"""

    def __init__(self):
        self.setup_logging()

    def setup_logging(self):
        """Setup logging to STDOUT only"""
        log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"

        # Configure root logger for STDOUT only
        logging.basicConfig(
            level=getattr(logging, ExpressConfig.LOG_LEVEL),
            format=log_format,
            datefmt=date_format,
            stream=sys.stdout,
            force=True,
        )

        self.logger = logging.getLogger("ExpressFastAGI")

        # Redirect Twisted logs to Python logging
        observer = twisted_log.PythonLoggingObserver()
        observer.start()

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
    ULINE is a simple unique number (1-199) assigned to each call
    Used for call parking and pickup via PAGINGEXTEN
    """

    def __init__(self):
        # Storage: ULINE -> (cdr_start, cdr_uniqueid, channel, timestamp)
        self.ulines: Dict[int, Tuple[str, str, str, datetime]] = {}
        # Reverse lookup: cdr_uniqueid -> ULINE
        self.uniqueid_to_uline: Dict[str, int] = {}

    def allocate_uline(
        self, cdr_start: str, cdr_uniqueid: str, channel: str
    ) -> Optional[int]:
        """
        Allocate a new ULINE for a call

        Args:
            cdr_start: CDR start time
            cdr_uniqueid: CDR unique ID
            channel: Channel name

        Returns:
            Allocated ULINE number or None if all lines are busy
        """
        # Check if this call already has a ULINE
        if cdr_uniqueid in self.uniqueid_to_uline:
            existing_uline = self.uniqueid_to_uline[cdr_uniqueid]
            logger.info(
                f"Call {cdr_uniqueid} already has ULINE {existing_uline}, returning existing"
            )
            return existing_uline

        # Find available ULINE
        for uline in range(ExpressConfig.ULINE_MIN, ExpressConfig.ULINE_MAX + 1):
            if uline not in self.ulines:
                # Allocate this ULINE
                timestamp = datetime.now()
                self.ulines[uline] = (cdr_start, cdr_uniqueid, channel, timestamp)
                self.uniqueid_to_uline[cdr_uniqueid] = uline

                logger.info(
                    f"Allocated ULINE {uline} for call {cdr_uniqueid} (channel: {channel})"
                )
                return uline

        logger.error(
            f"No available ULINEs! All {ExpressConfig.ULINE_MIN}-{ExpressConfig.ULINE_MAX} are busy"
        )
        return None

    def update_uline(self, cdr_uniqueid: str, new_channel: str) -> Optional[int]:
        """
        Update ULINE when call is parked or transferred

        Args:
            cdr_uniqueid: CDR unique ID
            new_channel: New channel name (e.g., parked channel)

        Returns:
            ULINE number or None if not found
        """
        if cdr_uniqueid not in self.uniqueid_to_uline:
            logger.warning(f"Cannot update ULINE: Call {cdr_uniqueid} not found")
            return None

        uline = self.uniqueid_to_uline[cdr_uniqueid]
        cdr_start, _, old_channel, _ = self.ulines[uline]
        timestamp = datetime.now()

        self.ulines[uline] = (cdr_start, cdr_uniqueid, new_channel, timestamp)

        logger.info(
            f"Updated ULINE {uline} for call {cdr_uniqueid}: {old_channel} -> {new_channel}"
        )
        return uline

    def release_uline(self, cdr_uniqueid: str) -> bool:
        """
        Release ULINE when call ends

        Args:
            cdr_uniqueid: CDR unique ID

        Returns:
            True if released, False if not found
        """
        if cdr_uniqueid not in self.uniqueid_to_uline:
            logger.warning(f"Cannot release ULINE: Call {cdr_uniqueid} not found")
            return False

        uline = self.uniqueid_to_uline[cdr_uniqueid]
        del self.ulines[uline]
        del self.uniqueid_to_uline[cdr_uniqueid]

        logger.info(f"Released ULINE {uline} for call {cdr_uniqueid}")
        return True

    def get_uline_info(self, uline: int) -> Optional[Dict]:
        """Get information about a ULINE"""
        if uline not in self.ulines:
            return None

        cdr_start, cdr_uniqueid, channel, timestamp = self.ulines[uline]
        return {
            "uline": uline,
            "cdr_start": cdr_start,
            "cdr_uniqueid": cdr_uniqueid,
            "channel": channel,
            "timestamp": timestamp.isoformat(),
        }

    def get_stats(self) -> Dict:
        """Get ULINE usage statistics"""
        total_slots = ExpressConfig.ULINE_MAX - ExpressConfig.ULINE_MIN + 1
        used_slots = len(self.ulines)
        free_slots = total_slots - used_slots

        return {
            "total": total_slots,
            "used": used_slots,
            "free": free_slots,
            "usage_percent": round((used_slots / total_slots) * 100, 2),
        }


# Global ULINE manager instance
uline_manager = ULineManager()


class AsteriskHelper:
    """Helper methods for Asterisk operations"""

    @staticmethod
    def normalize_phone_number(callerid: str) -> str:
        """
        Extract last 10 digits from CallerID (Ukrainian format)

        Args:
            callerid: CallerID from Asterisk (may contain +38, 38, 0, etc.)

        Returns:
            Normalized number (last 10 digits)
        """
        # Remove all non-digit characters
        digits = re.sub(r"\D", "", callerid)

        # Take last 10 digits
        if len(digits) >= 10:
            return digits[-10:]
        return digits

    @staticmethod
    def extract_member_peer(member_interface: str) -> Optional[str]:
        """
        Extract peer name from MEMBERINTERFACE

        Args:
            member_interface: MEMBERINTERFACE from Asterisk (e.g., SIP/1001, PJSIP/1001)

        Returns:
            Peer name or None
        """
        if not member_interface:
            return None

        parts = member_interface.split("/")
        if len(parts) >= 2:
            return parts[1].split("-")[0]  # Remove channel suffix

        return None

    @staticmethod
    async def get_peer_ip_async(agi, member_interface: str) -> str:
        """
        Get IP address of peer (async version)

        Args:
            agi: AGI object
            member_interface: MEMBERINTERFACE from Asterisk

        Returns:
            IP address or 'unknown'
        """
        if not member_interface:
            return "unknown"

        try:
            # For PJSIP
            if "PJSIP" in member_interface.upper():
                result = await agi.getVariable("CHANNEL(pjsip,remote_addr)")
                if result and result != "":
                    ip = result.split(":")[0]
                    return ip

            # For SIP
            elif "SIP" in member_interface.upper():
                result = await agi.getVariable("CHANNEL(recvip)")
                if result and result != "":
                    ip = result.split(":")[0]
                    return ip

            # Alternative method - via SIPCHANINFO
            result = await agi.getVariable("SIPCHANINFO(recvip)")
            if result and result != "":
                ip = result.split(":")[0]
                return ip

        except Exception as e:
            logger.warning(f"Error getting peer IP: {e}")

        return "unknown"


class ExpressHTTPClient:
    """HTTP client for Express Taxi API"""

    @staticmethod
    async def send_incoming_call(
        server_url: str,
        provider: str,
        caller_id: str,
        member_ip: str,
        uline: int,
        car_class: str,
    ) -> Dict:
        """
        Send HTTP request to Express API about incoming call

        Args:
            server_url: Full URL to Express API endpoint
            provider: Provider ID
            caller_id: Caller phone number (normalized)
            member_ip: Operator IP address
            uline: Unique line number
            car_class: Car class

        Returns:
            Dict with request result
        """
        # Parse URL to extract base
        parsed = urlparse(server_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Build query parameters
        params = {
            "provider": provider,
            "from": caller_id,
            "to": member_ip,
            "line": str(uline),
            "carClass": car_class,
        }

        # Add existing query params from server_url
        if parsed.query:
            for param in parsed.query.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    if key not in params:
                        params[key] = value

        full_url = f"{base_url}?{urlencode(params)}"

        logger.info(f"Sending request to Express: {full_url}")

        try:
            timeout = aiohttp.ClientTimeout(total=ExpressConfig.HTTP_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(full_url) as response:
                    status = response.status
                    content = await response.text()

                    if status == 200:
                        logger.info(f"Express response: {content}")
                        return {"success": True, "status": status, "content": content}
                    else:
                        logger.error(f"Express HTTP error {status}: {content}")
                        return {"success": False, "status": status, "content": content}

        except asyncio.TimeoutError:
            error_msg = f"Timeout connecting to Express ({ExpressConfig.HTTP_TIMEOUT}s)"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"HTTP request error: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}


@defer.inlineCallbacks
def express_incoming_call_handler(agi):
    """
    Main FastAGI handler for Express incoming calls

    Handles:
    1. ULINE allocation for the call
    2. Getting operator IP address
    3. Sending notification to Express API

    Args:
        agi: StarPy AGI object
    """
    try:
        logger.info("=" * 60)
        logger.info("Express FastAGI: New request")
        logger.info(f"Channel: {agi.variables.get('agi_channel', 'unknown')}")
        logger.info(f"CallerID: {agi.variables.get('agi_callerid', 'unknown')}")

        # Get CDR information for ULINE
        cdr_start = yield agi.getVariable("CDR(start)")
        cdr_uniqueid = yield agi.getVariable("CDR(uniqueid)")
        channel = agi.variables.get("agi_channel", "")

        if not cdr_start:
            cdr_start = "unknown"
        if not cdr_uniqueid:
            cdr_uniqueid = "unknown"

        logger.info(f"CDR start: {cdr_start}")
        logger.info(f"CDR uniqueid: {cdr_uniqueid}")

        # Allocate ULINE
        uline = uline_manager.allocate_uline(cdr_start, cdr_uniqueid, channel)

        if uline is None:
            error_msg = "Failed to allocate ULINE - all lines busy"
            logger.error(error_msg)
            yield agi.verbose(error_msg, 1)

            # Still continue with processing, use ULINE=0 as fallback
            uline = 0
        else:
            # Set ULINE as channel variable for Asterisk
            yield agi.setVariable("ULINE", str(uline))
            yield agi.verbose(f"Allocated ULINE: {uline}", 2)

            # Log ULINE stats
            stats = uline_manager.get_stats()
            logger.info(
                f"ULINE stats: {stats['used']}/{stats['total']} used ({stats['usage_percent']}%)"
            )

        # Read MEMBERINTERFACE
        member_interface = yield agi.getVariable("MEMBERINTERFACE")
        logger.info(f"MEMBERINTERFACE: {member_interface}")

        # Get operator IP address
        member_ip = yield AsteriskHelper.get_peer_ip_async(agi, member_interface)
        logger.info(f"Member IP: {member_ip}")

        # Read and normalize CallerID
        callerid_raw = yield agi.getVariable("CALLERID(num)")
        if not callerid_raw:
            callerid_raw = agi.variables.get("agi_callerid", "")

        caller_id = AsteriskHelper.normalize_phone_number(callerid_raw)
        logger.info(f"CallerID: {callerid_raw} -> {caller_id}")

        # Read EXPRESS_PROVIDER
        express_provider = yield agi.getVariable("EXPRESS_PROVIDER")
        if not express_provider:
            express_provider = ExpressConfig.DEFAULT_EXPRESS_PROVIDER
        logger.info(f"EXPRESS_PROVIDER: {express_provider}")

        # Read EXPRESS_CLASS
        express_class = yield agi.getVariable("EXPRESS_CLASS")
        if not express_class:
            express_class = ExpressConfig.DEFAULT_EXPRESS_CLASS
        logger.info(f"EXPRESS_CLASS: {express_class}")

        # Read EXPRESS_URL
        express_url = yield agi.getVariable("EXPRESS_URL")
        if not express_url:
            express_url = ExpressConfig.DEFAULT_EXPRESS_URL

        if not express_url:
            error_msg = "EXPRESS_URL not set!"
            logger.error(error_msg)
            yield agi.verbose(error_msg, 1)
            defer.returnValue(None)

        logger.info(f"EXPRESS_URL: {express_url}")

        # Send HTTP request to Express
        yield agi.verbose("Sending request to Express...", 2)

        result = yield defer.inlineCallbacks(
            lambda: ExpressHTTPClient.send_incoming_call(
                express_url,
                express_provider,
                caller_id,
                member_ip,
                uline,
                express_class,
            )
        )()

        if result.get("success"):
            yield agi.verbose("Express request successful", 2)
            logger.info("Express request completed successfully")
        else:
            error = result.get("error", result.get("content", "Unknown error"))
            yield agi.verbose(f"Express error: {error}", 1)
            logger.error(f"Express request failed: {error}")

        logger.info("Express FastAGI: Request completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Critical error in handler: {str(e)}", exc_info=True)
        try:
            yield agi.verbose(f"Error: {str(e)}", 1)
        except Exception:
            pass

    defer.returnValue(None)


@defer.inlineCallbacks
def express_uline_update_handler(agi):
    """
    FastAGI handler for updating ULINE when call is parked

    Args:
        agi: StarPy AGI object
    """
    try:
        logger.info("=" * 60)
        logger.info("Express FastAGI: ULINE update request")

        # Get CDR uniqueid
        cdr_uniqueid = yield agi.getVariable("CDR(uniqueid)")
        channel = agi.variables.get("agi_channel", "")

        if not cdr_uniqueid:
            error_msg = "CDR(uniqueid) not available"
            logger.error(error_msg)
            yield agi.verbose(error_msg, 1)
            defer.returnValue(None)

        logger.info(f"CDR uniqueid: {cdr_uniqueid}")
        logger.info(f"New channel: {channel}")

        # Update ULINE
        uline = uline_manager.update_uline(cdr_uniqueid, channel)

        if uline is not None:
            yield agi.setVariable("ULINE", str(uline))
            yield agi.verbose(f"Updated ULINE: {uline}", 2)
            logger.info(f"ULINE {uline} updated successfully")
        else:
            error_msg = "Failed to update ULINE - call not found"
            logger.warning(error_msg)
            yield agi.verbose(error_msg, 1)

        logger.info("Express FastAGI: ULINE update completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in ULINE update handler: {str(e)}", exc_info=True)
        try:
            yield agi.verbose(f"Error: {str(e)}", 1)
        except Exception:
            pass

    defer.returnValue(None)


@defer.inlineCallbacks
def express_uline_release_handler(agi):
    """
    FastAGI handler for releasing ULINE when call ends

    Args:
        agi: StarPy AGI object
    """
    try:
        logger.info("=" * 60)
        logger.info("Express FastAGI: ULINE release request")

        # Get CDR uniqueid
        cdr_uniqueid = yield agi.getVariable("CDR(uniqueid)")

        if not cdr_uniqueid:
            error_msg = "CDR(uniqueid) not available"
            logger.error(error_msg)
            yield agi.verbose(error_msg, 1)
            defer.returnValue(None)

        logger.info(f"CDR uniqueid: {cdr_uniqueid}")

        # Release ULINE
        success = uline_manager.release_uline(cdr_uniqueid)

        if success:
            yield agi.verbose("ULINE released", 2)
            logger.info("ULINE released successfully")

            # Log stats
            stats = uline_manager.get_stats()
            logger.info(
                f"ULINE stats: {stats['used']}/{stats['total']} used ({stats['usage_percent']}%)"
            )
        else:
            error_msg = "Failed to release ULINE - call not found"
            logger.warning(error_msg)
            yield agi.verbose(error_msg, 1)

        logger.info("Express FastAGI: ULINE release completed")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in ULINE release handler: {str(e)}", exc_info=True)
        try:
            yield agi.verbose(f"Error: {str(e)}", 1)
        except Exception:
            pass

    defer.returnValue(None)


def route_handler(agi):
    """
    Route requests to appropriate handlers based on script name

    Args:
        agi: StarPy AGI object

    Returns:
        Deferred to appropriate handler
    """
    script = agi.variables.get("agi_network_script", "")

    logger.info(f"Routing request: script={script}")

    if script == "update":
        return express_uline_update_handler(agi)
    elif script == "release":
        return express_uline_release_handler(agi)
    else:
        # Default: incoming call handler
        return express_incoming_call_handler(agi)


def main():
    """Main function to start FastAGI server"""
    logger.info("=" * 60)
    logger.info("Express FastAGI Service Starting...")
    logger.info("Version: 2.0.0")
    logger.info(f"Host: {ExpressConfig.FASTAGI_HOST}")
    logger.info(f"Port: {ExpressConfig.FASTAGI_PORT}")
    logger.info(f"Log Level: {ExpressConfig.LOG_LEVEL}")
    logger.info(f"ULINE Range: {ExpressConfig.ULINE_MIN}-{ExpressConfig.ULINE_MAX}")
    logger.info("=" * 60)

    try:
        # Create FastAGI factory with routing
        factory = fastagi.FastAGIFactory(route_handler)

        # Start server
        reactor.listenTCP(
            ExpressConfig.FASTAGI_PORT, factory, interface=ExpressConfig.FASTAGI_HOST
        )

        logger.info(
            f"FastAGI server started on {ExpressConfig.FASTAGI_HOST}:{ExpressConfig.FASTAGI_PORT}"
        )
        logger.info("Waiting for connections from Asterisk...")
        logger.info("Available endpoints:")
        logger.info("  - agi://host:4574         (incoming call handler)")
        logger.info("  - agi://host:4574/update  (ULINE update)")
        logger.info("  - agi://host:4574/release (ULINE release)")

        # Start reactor
        reactor.run()

    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
