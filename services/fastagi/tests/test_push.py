"""
Tests for send_push() in fastagi.py (urlopen is mocked).

Run:
    cd services/fastagi
    pytest tests/test_push.py -v
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _mod in [
    "asterisk",
    "asterisk.ami",
    "starpy",
    "starpy.fastagi",
    "starpy.error",
    "twisted",
    "twisted.internet",
    "twisted.internet.reactor",
    "twisted.internet.defer",
    "sqlalchemy",
    "sqlalchemy.orm",
    "sqlalchemy.orm.declarative_base",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.modules["twisted.internet"].reactor = MagicMock()
sys.modules["twisted.internet.defer"].Deferred = MagicMock
sys.modules["twisted.internet.defer"].inlineCallbacks = lambda f: f
sys.modules["starpy.error"].AGICommandFailure = Exception


def test_send_push_request_shape():
    import fastagi as fagi

    with patch.object(fagi, "PBX_ID", "pbx-1"), patch.object(
        fagi, "PBX_SECRET", "s3cret"
    ), patch.object(fagi, "PUSH_SERVER_URL", "https://push.example/"), patch.object(
        fagi.urllib.request, "urlopen"
    ) as urlopen:
        fagi.send_push("101", "380671234567", "uid-1")

    req = urlopen.call_args.args[0]
    assert req.full_url == "https://push.example/client/message"
    assert req.get_header("Authorization") == "Bearer s3cret"
    assert json.loads(req.data) == {
        "pbx_id": "pbx-1",
        "username": "101",
        "message": "Incoming call from 380671234567",
        "push_type": "voip",
        "data": {"caller": "380671234567", "call_id": "uid-1"},
    }
    assert urlopen.call_args.kwargs["timeout"] == 5
