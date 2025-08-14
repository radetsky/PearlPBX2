# reports/templatetags/math_filters.py
from django import template

register = template.Library()


@register.filter
def div(value, arg):
    """Divide value by arg (float division)."""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


@register.filter
def mul(value, arg):
    """Multiply value by arg."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return None


@register.filter
def sub(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return None


@register.filter
def add(value, arg):
    """Add arg to value."""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return None
