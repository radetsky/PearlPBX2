class DialplanGuardedDeleteAdminMixin:
    """has_delete_permission() for a model whose delete() raises ValidationError
    when its `name` is still referenced by dialplan text (TrunkGroup, Queue) —
    hides the delete button instead of letting the confirm page 500 after the
    click.

    Django's own bulk "Delete selected" action calls has_delete_permission(request,
    obj) for every selected object too (via get_deleted_objects()) and refuses
    the whole batch if any one fails, so no separate delete_queryset() override
    is needed.
    """

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.find_dialplan_references(obj.name):
            return False
        return super().has_delete_permission(request, obj)
