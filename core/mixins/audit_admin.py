from django.utils.translation import gettext_lazy as _


class AuditAdminMixin:
    """ModelAdmin mixin for models extending core.models.AuditFields.

    Stamps created_by/modified_by from the requesting user and exposes the
    four audit fields as a read-only, collapsed fieldset.
    """

    readonly_fields = ["created_at", "modified_at", "created_by", "modified_by"]

    audit_fieldset = (
        _("Audit Information"),
        {
            "fields": ("created_at", "created_by", "modified_at", "modified_by"),
            "classes": ("collapse",),
        },
    )

    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)
