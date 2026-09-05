from rest_framework.permissions import BasePermission


class IsStaff(BasePermission):
    """Every method, read included, requires a staff or superuser account."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and (user.is_staff or user.is_superuser)
        )
