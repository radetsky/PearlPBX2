from django.utils.translation import gettext_lazy as _


class AuditAdminMixin:
    """ModelAdmin mixin for models extending core.models.AuditFields.

    Stamps created_by/modified_by from the requesting user and exposes the
    four audit fields as a read-only, collapsed fieldset. Subclasses declare
    only their own extra readonly fields (if any) in `readonly_fields` — the
    audit fields are unioned in by get_readonly_fields() regardless, so a
    subclass assigning its own `readonly_fields` can't accidentally drop them.
    """

    audit_readonly_fields = ["created_at", "modified_at", "created_by", "modified_by"]

    audit_fieldset = (
        _("Audit Information"),
        {
            "fields": ("created_at", "created_by", "modified_at", "modified_by"),
            "classes": ("collapse",),
        },
    )

    def get_readonly_fields(self, request, obj=None):
        return list(super().get_readonly_fields(request, obj)) + list(self.audit_readonly_fields)

    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)
