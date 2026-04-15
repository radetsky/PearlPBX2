import os
import re
import string
import secrets
import shutil
from os import makedirs

from django.conf import settings


def normalize_phone(phone: str) -> str:
    """Normalize a phone number to a consistent local format.

    Mirrors the JS normalizePhone() in new_dashboard.html.
    Uses PHONE_* settings for country/local codes and length constants.
    """
    digits = re.sub(r'\D', '', phone or '')
    if not digits:
        return phone
    country_code = getattr(settings, 'PHONE_COUNTRY_CODE', '380')
    local_code = getattr(settings, 'PHONE_LOCAL_CODE', '044')
    required_len = getattr(settings, 'PHONE_REQUIRED_LEN', 10)
    city_code_len = getattr(settings, 'PHONE_CITYCODE_LEN', 7)
    n = len(digits)
    if n == required_len:
        return digits
    if n > required_len and digits.startswith(country_code):
        return digits[n - required_len:]
    if n == city_code_len:
        return local_code + digits
    if n == required_len - 1:
        return '0' + digits
    return digits


def generate_password():
    alphabet = string.ascii_letters + string.digits
    while True:
        password = "".join(secrets.choice(alphabet) for i in range(10))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and sum(c.isdigit() for c in password) >= 3
        ):
            break
    return password


def generate_safe_password(len: int) -> string:
    return secrets.token_urlsafe(len)


def generate_32_char_password():
    return generate_safe_password(32)


def generate_64_char_password():
    return generate_safe_password(64)


def create_directory(path: str):
    """
    Create a directory if it doesn't exist.
    """
    makedirs(path, exist_ok=True)


def remove_directory(directory_path: str) -> bool:
    """
    Reсursive remove a directory if it exists.
    """
    # Check if the directory exists
    if os.path.exists(directory_path):
        try:
            shutil.rmtree(directory_path)
            return True
        except PermissionError as e:
            raise PermissionError(e)
        except OSError as e:
            raise OSError(e)
    else:
        return False
