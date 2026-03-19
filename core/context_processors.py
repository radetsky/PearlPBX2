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
    user = request.user
    user_group_names = (
        {g.name for g in user.groups.all()} if user.is_authenticated else set()
    )

    def _has_role(role: str) -> bool:
        if not user.is_authenticated:
            return False
        if role == "superuser":
            return user.is_superuser
        if role == "admin":
            return user.is_staff
        return role in user_group_names

    filtered_menu = [
        item
        for item in settings.HEADER_MENU_PAGES
        if any(_has_role(role) for role in item.get("allowed_roles", []))
    ]
    return {
        "allowed_header_menu_items": filtered_menu,
        "selected_header_menu_item": next(
            (
                item
                for item in filtered_menu
                if request.path.startswith(item["url"])
            ),
            None,
        ),
    }
