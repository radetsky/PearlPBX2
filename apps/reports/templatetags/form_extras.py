# templatetags/form_extras.py - розширена версія
from django import template

register = template.Library()


@register.filter
def add_class(field, css_class):
    """Додає CSS клас до поля форми"""
    if hasattr(field, "as_widget"):
        return field.as_widget(attrs={"class": css_class})
    return field


@register.filter
def channel_name(channel):
    """
    Витягує назву каналу без номера
    Обробляє різні формати каналів Asterisk

    Приклади:
    'SIP/1001-00000123' -> 'SIP/1001'
    'PJSIP/1001-00000123' -> 'PJSIP/1001'
    'IAX2/provider-00000123' -> 'IAX2/provider'
    'Local/1001@internal-00000123;1' -> 'Local/1001@internal'
    'DAHDI/1-1' -> 'DAHDI/1'
    """
    if not channel:
        return ""

    # Основне розділення по дефісу
    base_channel = channel.split("-")[0]

    # Для Local каналів також прибираємо ;1 або ;2 в кінці
    if base_channel.startswith("Local/"):
        base_channel = base_channel.split(";")[0]

    return base_channel


@register.filter
def channel_type(channel):
    """
    Витягує тільки тип каналу (SIP, PJSIP, IAX2, тощо)

    Приклади:
    'SIP/1001-00000123' -> 'SIP'
    'PJSIP/1001-00000123' -> 'PJSIP'
    """
    if not channel:
        return ""

    channel_name = channel.split("-")[0]  # Прибираємо номер
    return channel_name.split("/")[0]  # Беремо тільки тип


@register.filter
def channel_endpoint(channel):
    """
    Витягує кінцеву точку каналу (номер, trunk, тощо)

    Приклади:
    'SIP/1001-00000123' -> '1001'
    'PJSIP/trunk_provider-00000123' -> 'trunk_provider'
    """
    if not channel:
        return ""

    channel_name = channel.split("-")[0]  # Прибираємо номер
    if "/" in channel_name:
        endpoint = channel_name.split("/", 1)[1]  # Беремо все після першого /
        # Для Local каналів прибираємо @context та ;1/;2
        if "@" in endpoint:
            endpoint = endpoint.split("@")[0]
        if ";" in endpoint:
            endpoint = endpoint.split(";")[0]
        return endpoint
    return channel_name


@register.filter
def format_channel(channel):
    """
    Форматує канал для красивого відображення

    Приклади:
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
    """
    Конвертує секунди в формат mm:ss
    """
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
    Конвертує секунди в формат hh:mm:ss (для довгих дзвінків)

    Приклади:
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
    Розумний формат - показує години тільки якщо вони є

    Приклади:
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
    Людський формат тривалості

    Приклади:
    65 -> "1 хв 5 с"
    3661 -> "1 год 1 хв 1 с"
    120 -> "2 хв"
    """
    try:
        total_seconds = int(seconds or 0)

        if total_seconds == 0:
            return "0 с"

        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        parts = []
        if hours > 0:
            parts.append(f"{hours} год")
        if minutes > 0:
            parts.append(f"{minutes} хв")
        if secs > 0 or not parts:  # показуємо секунди якщо це єдина одиниця
            parts.append(f"{secs} с")

        return " ".join(parts)
    except (ValueError, TypeError):
        return "0 с"


@register.filter
def duration_class(seconds):
    """
    Повертає CSS клас базуючись на тривалості дзвінка
    Корисно для кольорового кодування
    """
    try:
        total_seconds = int(seconds or 0)

        if total_seconds == 0:
            return "duration-zero"
        elif total_seconds < 30:
            return "duration-short"  # червоний - короткі дзвінки
        elif total_seconds < 300:  # 5 хвилин
            return "duration-medium"  # жовтий - середні дзвінки
        else:
            return "duration-long"  # зелений - довгі дзвінки
    except (ValueError, TypeError):
        return "duration-zero"


@register.filter
def index(sequence, position):
    try:
        return sequence[position]
    except (IndexError, TypeError):
        return ""
