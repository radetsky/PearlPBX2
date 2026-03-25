"""
Tests for ULineRedisManager (uline_redis.py).

Requirements:
    pip install pytest fakeredis[lua]

Run:
    cd services/fastagi
    source .python-venv/bin/activate
    pytest tests/test_uline_redis.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import fakeredis
from uline_redis import ULineRedisManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def r():
    """Shared fakeredis instance with Lua support."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def manager(r):
    """ULineRedisManager with a small slot range (1–5) for easier testing."""
    mgr = ULineRedisManager(redis_client=r)
    mgr.min_slot = 1
    mgr.max_slot = 5
    return mgr


# ---------------------------------------------------------------------------
# allocate()
# ---------------------------------------------------------------------------


class TestAllocate:
    def test_returns_slot_number(self, manager):
        slot = manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        assert slot is not None
        assert 1 <= slot <= 5

    def test_allocates_from_lowest_slot(self, manager):
        slot = manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        assert slot == 1

    def test_sequential_allocation(self, manager):
        s1 = manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        s2 = manager.allocate("uid-2", "PJSIP/102", "2024-01-01", "102")
        assert s1 == 1
        assert s2 == 2

    def test_idempotent_same_uniqueid(self, manager):
        s1 = manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        s2 = manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        assert s1 == s2

    def test_returns_none_when_all_slots_full(self, manager):
        for i in range(1, 6):  # fill all 5 slots
            manager.allocate(f"uid-{i}", f"PJSIP/10{i}", "2024-01-01", str(i))
        result = manager.allocate("uid-extra", "PJSIP/200", "2024-01-01", "200")
        assert result is None

    def test_redis_keys_created(self, r, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        assert r.exists("parking:uline:1")
        assert r.exists("parking:uid:uid-1")

    def test_slot_hash_fields(self, r, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        data = r.hgetall("parking:uline:1")
        assert data["uniqueid"] == "uid-1"
        assert data["channel"] == "PJSIP/101"
        assert data["caller_id"] == "101"
        assert data["cdr_start"] == "2024-01-01"
        assert "allocated_at" in data

    def test_uid_key_points_to_slot(self, r, manager):
        slot = manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        assert r.get("parking:uid:uid-1") == str(slot)

    def test_ttl_is_set(self, r, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        assert r.ttl("parking:uline:1") > 0
        assert r.ttl("parking:uid:uid-1") > 0


# ---------------------------------------------------------------------------
# release()
# ---------------------------------------------------------------------------


class TestRelease:
    def test_releases_existing_slot(self, r, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        result = manager.release("uid-1")
        assert result is True
        assert not r.exists("parking:uline:1")
        assert not r.exists("parking:uid:uid-1")

    def test_slot_reusable_after_release(self, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        manager.release("uid-1")
        new_slot = manager.allocate("uid-2", "PJSIP/102", "2024-01-01", "102")
        assert new_slot == 1

    def test_returns_false_for_unknown_uniqueid(self, manager):
        result = manager.release("uid-nonexistent")
        assert result is False

    def test_partial_fill_release_middle(self, r, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        manager.allocate("uid-2", "PJSIP/102", "2024-01-01", "102")
        manager.allocate("uid-3", "PJSIP/103", "2024-01-01", "103")
        manager.release("uid-2")
        assert not r.exists("parking:uline:2")
        assert r.exists("parking:uline:1")
        assert r.exists("parking:uline:3")


# ---------------------------------------------------------------------------
# flush_all()
# ---------------------------------------------------------------------------


class TestFlushAll:
    def test_clears_all_keys(self, r, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        manager.allocate("uid-2", "PJSIP/102", "2024-01-01", "102")
        count = manager.flush_all()
        assert count == 4  # 2 uline keys + 2 uid keys
        assert list(r.scan_iter("parking:*")) == []

    def test_flush_empty_returns_zero(self, manager):
        count = manager.flush_all()
        assert count == 0

    def test_slots_allocatable_after_flush(self, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        manager.flush_all()
        slot = manager.allocate("uid-new", "PJSIP/200", "2024-01-01", "200")
        assert slot == 1


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_empty_stats(self, manager):
        stats = manager.get_stats()
        assert stats["total"] == 5
        assert stats["used"] == 0
        assert stats["free"] == 5
        assert stats["usage_percent"] == 0.0

    def test_partial_usage_stats(self, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        manager.allocate("uid-2", "PJSIP/102", "2024-01-01", "102")
        stats = manager.get_stats()
        assert stats["used"] == 2
        assert stats["free"] == 3
        assert stats["total"] == 5
        assert stats["usage_percent"] == 40.0

    def test_full_usage_stats(self, manager):
        for i in range(1, 6):
            manager.allocate(f"uid-{i}", f"PJSIP/10{i}", "2024-01-01", str(i))
        stats = manager.get_stats()
        assert stats["used"] == 5
        assert stats["free"] == 0
        assert stats["usage_percent"] == 100.0

    def test_stats_after_release(self, manager):
        manager.allocate("uid-1", "PJSIP/101", "2024-01-01", "101")
        manager.release("uid-1")
        stats = manager.get_stats()
        assert stats["used"] == 0
        assert stats["free"] == 5
