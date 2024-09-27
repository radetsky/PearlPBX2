import string
import secrets


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
