import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import validate_ipv4_address

import logging

logger = logging.getLogger(__name__)


def validate_bind_ip(value):
    items = value.split(":")
    logger.info(value)
    validate_ipv4_address(items[0])
    if len(items) > 1:
        try:
            port = int(items[1])
            if port < 1024 or port > 65535:
                raise ValidationError(
                    _("%(value)s is not a valid port"),
                    params={"value": items[1]},
                )
        except ValueError:
            raise ValidationError(
                _("%(value)s is not a valid port"),
                params={"value": items[1]},
            )


def validate_asterisk_context(value):
    """Validator for Asterisk context name"""
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", value):
        raise ValidationError(
            "Context name must start with letter or underscore, "
            "and contain only letters, digits, underscores, and hyphens."
        )
    if len(value) > 80:
        raise ValidationError("Context name is too long (max 80 characters).")
