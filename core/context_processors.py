from django.conf import settings
from django.http import HttpRequest


def template_config_context_processor(request: HttpRequest):
    return {
        "TEMPLATE_DATE_FORMAT": settings.TEMPLATE_DATE_FORMAT,
        "TEMPLATE_TIME_FORMAT": settings.TEMPLATE_TIME_FORMAT,
        "TEMPLATE_DATETIME_FORMAT": settings.TEMPLATE_DATETIME_FORMAT,
        "TEMPLATE_MOMENT_DATETIME_FORMAT": settings.TEMPLATE_MOMENT_DATETIME_FORMAT,
        "TEMPLATE_POPUP_TIMEOUT_MS": settings.TEMPLATE_POPUP_TIMEOUT_MS,
    }


def header_menu_context_processor(request: HttpRequest):
    return {
        "allowed_header_menu_items": settings.HEADER_MENU_PAGES,
        "selected_header_menu_item": next(
            (
                item
                for item in settings.HEADER_MENU_PAGES
                if request.path.startswith(item["url"])
            ),
            None,
        ),
    }
