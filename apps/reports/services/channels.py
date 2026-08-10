"""Helpers to classify Asterisk PJSIP channels as internal (SIPUser) or external (SIPPeer).

A channel string looks like ``PJSIP/<endpoint-name>-<sequence>``. The endpoint
name identifies either a SIPPeer (trunk/provider) or a SIPUser (registered
internal extension).
"""

import re

from core.models import SIPPeer, SIPUser


def _channel_regex(names):
    """Build a `^PJSIP/(name1|name2|...)-` regex from endpoint names, or None if empty."""
    if not names:
        return None
    return r"^PJSIP/(" + "|".join(re.escape(n) for n in names) + r")-"


def peer_channel_regex():
    """Regex matching channels whose endpoint is a SIPPeer (external/trunk), or None."""
    return _channel_regex(list(SIPPeer.objects.values_list("name", flat=True)))


def user_channel_regex():
    """Regex matching channels whose endpoint is a SIPUser (internal extension), or None."""
    return _channel_regex(list(SIPUser.objects.values_list("username", flat=True)))
