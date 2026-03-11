# templatetags/form_extras.py
from django import template

register = template.Library()


@register.filter
def add_class(field, css_class):
    """Add a CSS class to a form field widget."""
    if hasattr(field, "as_widget"):
        return field.as_widget(attrs={"class": css_class})
    return field


@register.filter
def channel_name(channel):
    """
    Extract channel name without the unique suffix.

    Examples:
    'SIP/1001-00000123' -> 'SIP/1001'
    'PJSIP/1001-00000123' -> 'PJSIP/1001'
    'IAX2/provider-00000123' -> 'IAX2/provider'
    'Local/1001@internal-00000123;1' -> 'Local/1001@internal'
    'DAHDI/1-1' -> 'DAHDI/1'
    """
    if not channel:
        return ""

    base_channel = channel.split("-")[0]

    # Strip ;1 / ;2 suffix from Local channels
    if base_channel.startswith("Local/"):
        base_channel = base_channel.split(";")[0]

    return base_channel


@register.filter
def channel_type(channel):
    """
    Extract channel technology (SIP, PJSIP, IAX2, etc.).

    Examples:
    'SIP/1001-00000123' -> 'SIP'
    'PJSIP/1001-00000123' -> 'PJSIP'
    """
    if not channel:
        return ""

    channel_name = channel.split("-")[0]  # strip unique suffix
    return channel_name.split("/")[0]  # keep only the technology part


@register.filter
def channel_endpoint(channel):
    """
    Extract the channel endpoint (extension, trunk name, etc.).

    Examples:
    'SIP/1001-00000123' -> '1001'
    'PJSIP/trunk_provider-00000123' -> 'trunk_provider'
    """
    if not channel:
        return ""

    channel_name = channel.split("-")[0]  # strip unique suffix
    if "/" in channel_name:
        endpoint = channel_name.split("/", 1)[1]  # everything after the first /
        # Strip @context and ;1/;2 from Local channels
        if "@" in endpoint:
            endpoint = endpoint.split("@")[0]
        if ";" in endpoint:
            endpoint = endpoint.split(";")[0]
        return endpoint
    return channel_name


@register.filter
def format_channel(channel):
    """
    Format a channel string for display.

    Examples:
    'SIP/1001-00000123' -> 'SIP: 1001'
    'PJSIP/trunk_provider-00000123' -> 'PJSIP: trunk_provider'
    """
    if not channel:
        return ""

    channel_type_val = channel_type(channel)
    channel_endpoint_val = channel_endpoint(channel)

    if channel_type_val and channel_endpoint_val:
        return f"{channel_type_val}: {channel_endpoint_val}"

    return channel_name(channel)


@register.filter
def duration_format(seconds):
    """Convert seconds to mm:ss format."""
    try:
        total_seconds = int(seconds or 0)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    except (ValueError, TypeError):
        return "00:00"


@register.filter
def duration_hms(seconds):
    """
    Convert seconds to hh:mm:ss format.

    Examples:
    65 -> "00:01:05"
    3661 -> "01:01:01"
    """
    try:
        total_seconds = int(seconds or 0)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except (ValueError, TypeError):
        return "00:00:00"


@register.filter
def duration_smart(seconds):
    """
    Smart format — show hours only when present.

    Examples:
    65 -> "01:05"
    3661 -> "1:01:01"
    """
    try:
        total_seconds = int(seconds or 0)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "00:00"


@register.filter
def duration_human(seconds):
    """
    Human-readable duration format.

    Examples:
    65 -> "1m 5s"
    3661 -> "1h 1m 1s"
    120 -> "2m"
    """
    try:
        total_seconds = int(seconds or 0)

        if total_seconds == 0:
            return "0s"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if secs > 0 or not parts:
            parts.append(f"{secs}s")

        return " ".join(parts)
    except (ValueError, TypeError):
        return "0s"


@register.filter
def duration_class(seconds):
    """Return a CSS class based on call duration for color-coding."""
    try:
        total_seconds = int(seconds or 0)

        if total_seconds == 0:
            return "duration-zero"
        elif total_seconds < 30:
            return "duration-short"
        elif total_seconds < 300:
            return "duration-medium"
        else:
            return "duration-long"
    except (ValueError, TypeError):
        return "duration-zero"


@register.filter
def index(sequence, position):
    try:
        return sequence[position]
    except (IndexError, TypeError):
        return ""


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
