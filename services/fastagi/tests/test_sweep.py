"""
Tests for sweep_parking_ulines() in fastagi.py.

Uses unittest.mock to patch the module-level redis_client and reactor,
so no real Redis or Twisted reactor is needed.

Run:
    cd services/fastagi
    source .python-venv/bin/activate
    pytest tests/test_sweep.py -v
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock heavy dependencies that are not needed for sweep tests
# before fastagi.py is imported.
from unittest.mock import MagicMock

for _mod in [
    "asterisk", "asterisk.ami",
    "starpy", "starpy.fastagi", "starpy.error",
    "twisted", "twisted.internet", "twisted.internet.reactor",
    "twisted.internet.defer",
    "sqlalchemy", "sqlalchemy.orm", "sqlalchemy.orm.declarative_base",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Specific attributes needed at import time
sys.modules["twisted.internet"].reactor = MagicMock()
sys.modules["twisted.internet.defer"].Deferred = MagicMock
sys.modules["twisted.internet.defer"].inlineCallbacks = lambda f: f
sys.modules["starpy.error"].AGICommandFailure = Exception

import pytest
import fakeredis


def make_sweep(r):
    """
    Return sweep_parking_ulines with redis_client and reactor patched.
    """
    import fastagi as fagi
    fagi.redis_client = r
    fagi.reactor = MagicMock()
    return fagi.sweep_parking_ulines


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def sweep(r):
    return make_sweep(r)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_slot(r, slot: int, uniqueid: str, channel: str = "PJSIP/101"):
    r.hset(f"parking:uline:{slot}", mapping={
        "uniqueid": uniqueid,
        "channel": channel,
        "caller_id": "101",
        "cdr_start": "2024-01-01",
        "allocated_at": "2024-01-01T00:00:00+00:00",
    })
    r.set(f"parking:uid:{uniqueid}", str(slot))


def _mark_channel_active(r, uniqueid: str):
    """Simulate dashboard publishing an active channel key."""
    r.set(f"asterisk:uid:{uniqueid}", "1")
    r.set("asterisk:channels:all", "1")  # sentinel key


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSweepSkipsWhenDashboardOffline:
    def test_skips_if_no_sentinel_key(self, r, sweep):
        _add_slot(r, 1, "uid-1")
        sweep()
        # slot must NOT be released because dashboard is offline
        assert r.exists("parking:uline:1")
        assert r.exists("parking:uid:uid-1")


class TestSweepReleasesStaleSlots:
    def test_releases_slot_with_inactive_channel(self, r, sweep):
        r.set("asterisk:channels:all", "1")
        _add_slot(r, 1, "uid-stale")
        sweep()
        assert not r.exists("parking:uline:1")
        assert not r.exists("parking:uid:uid-stale")

    def test_keeps_slot_with_active_channel(self, r, sweep):
        r.set("asterisk:channels:all", "1")
        _add_slot(r, 1, "uid-active")
        _mark_channel_active(r, "uid-active")
        sweep()
        assert r.exists("parking:uline:1")
        assert r.exists("parking:uid:uid-active")

    def test_mixed_slots_selective_release(self, r, sweep):
        r.set("asterisk:channels:all", "1")
        _add_slot(r, 1, "uid-active")
        _add_slot(r, 2, "uid-stale")
        _mark_channel_active(r, "uid-active")
        sweep()
        assert r.exists("parking:uline:1")   # active — kept
        assert not r.exists("parking:uline:2")  # stale — released

    def test_no_slots_runs_without_error(self, r, sweep):
        r.set("asterisk:channels:all", "1")
        sweep()  # should not raise


class TestSweepReschedulesItself:
    def test_reactor_callLater_called(self, r, sweep):
        import fastagi as fagi
        r.set("asterisk:channels:all", "1")
        sweep()
        fagi.reactor.callLater.assert_called_once()
        args = fagi.reactor.callLater.call_args[0]
        assert args[1] is sweep  # second arg is the function itself
