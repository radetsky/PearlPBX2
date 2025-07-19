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


def validate_asterisk_extension_prefix(value):
    """
    Validator for Asterisk extension prefix (dialplan pattern).

    Asterisk pattern matching rules:
    - Starts with _ (underscore)
    - X - any digit 0-9
    - Z - any digit 1-9
    - N - any digit 2-9
    - [123] - one of the digits in brackets
    - [1-5] - digit range
    - . (dot) - one or more characters
    - ! (exclamation mark) - zero or more characters
    - Literals (digits, +, -, etc.)
    """

    if not value:
        return

    # Check if the value contains only digits
    if value.isdigit():
        # If the value is all digits, it is a valid pattern
        return

    # Check that it starts with _
    if not value.startswith('_'):
        raise ValidationError(
            _('Asterisk extension pattern must start with the "_" character'),
            code='missing_underscore'
        )

    # Remove the first character _ for further validation
    pattern = value[1:]

    if not pattern:
        raise ValidationError(
            _('Pattern cannot be empty after "_"'),
            code='empty_pattern'
        )

    # Regular expression for validating Asterisk pattern
    # Allowed characters: digits, X, Z, N, [ranges], +, -, ., !, spaces
    asterisk_pattern_regex = r'^[0-9XZN\[\]0-9\-\+\.\!\s]*$'

    if not re.match(asterisk_pattern_regex, pattern):
        raise ValidationError(
            _('Invalid characters in pattern. Allowed: digits, X, Z, N, [ranges], +, -, ., !'),
            code='invalid_characters'
        )

    # Check for correct square brackets usage
    if '[' in pattern or ']' in pattern:
        bracket_count = pattern.count('[')
        closing_bracket_count = pattern.count(']')

        if bracket_count != closing_bracket_count:
            raise ValidationError(
                _('Unbalanced square brackets in pattern'),
                code='unbalanced_brackets'
            )

        # Check that all opening brackets have corresponding closing brackets
        bracket_pairs = re.findall(r'\[[^\]]*\]', pattern)
        for pair in bracket_pairs:
            content = pair[1:-1]
            if not content:
                raise ValidationError(
                    _('Empty square brackets are not allowed'),
                    code='empty_brackets'
                )

            # Check ranges like [1-9]
            if '-' in content:
                parts = content.split('-')
                if len(parts) == 2:
                    try:
                        start, end = int(parts[0]), int(parts[1])
                        if start >= end or start < 0 or end > 9:
                            raise ValidationError(
                                _('Invalid range in brackets: %(content)s'),
                                params={'content': pair},
                                code='invalid_range'
                            )
                    except (ValueError, IndexError):
                        raise ValidationError(
                            _('Invalid range format: %(content)s'),
                            params={'content': pair},
                            code='invalid_range_format'
                        )

    # Check maximum length (Asterisk has a limit)
    if len(value) > 80:
        raise ValidationError(
            _('Pattern is too long (maximum 80 characters)'),
            code='too_long'
        )

    # Additional checks for common mistakes

    # Check that . and ! are not doubled after other special symbols
    if '..' in pattern or '!!' in pattern:
        raise ValidationError(
            _('Double wildcards (.., !!) are not recommended'),
            code='double_wildcards'
        )

    # Warning about potentially problematic patterns
    if pattern.endswith('X.') or pattern.endswith('Z.') or pattern.endswith('N.'):
        # This is not an error, but may be undesirable
        pass

