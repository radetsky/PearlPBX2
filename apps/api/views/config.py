import logging
import os
import uuid
from contextlib import contextmanager

import redis
from django.conf import settings

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.api.exceptions import Conflict
from apps.api.permissions import IsSuperUser
from apps.api.serializers import ApplyChangesSerializer
from core.ami import AsteriskManagementInterface
from core.conf import get_users_excluded_from_pjsip
from pbx.admin import ApplyChangesView as AdminApplyChangesView

logger = logging.getLogger(__name__)

_APPLY_LOCK_KEY = "apply_changes:lock"
_APPLY_LOCK_TTL = 300
# Compare-and-delete: only release the lock if it still holds *our* token, so
# a request whose TTL already expired (e.g. a slow hard restart) can't delete
# a lock a different, later request has since acquired.
_RELEASE_IF_OWNER_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)


@contextmanager
def _apply_lock():
    """Best-effort distributed lock so two concurrent applies don't interleave
    backup/write. Fails open (proceeds without the lock, logging a warning)
    if Redis itself is unreachable — Apply Changes must stay usable even when
    Redis is down, matching how apps.webhooks.sync/apps.dashboard.views treat
    Redis as best-effort rather than a hard dependency for this operation.
    """
    client = None
    holding = False
    token = uuid.uuid4().hex
    try:
        client = redis.Redis.from_url(settings.REDIS_URL)
        holding = bool(client.set(_APPLY_LOCK_KEY, token, nx=True, ex=_APPLY_LOCK_TTL))
        if not holding:
            raise Conflict("A configuration apply is already in progress.")
    except Conflict:
        raise
    except Exception as e:
        logger.warning(f"Apply Changes lock unavailable, proceeding without it: {e}")
    try:
        yield
    finally:
        if holding and client is not None:
            try:
                client.eval(_RELEASE_IF_OWNER_SCRIPT, 1, _APPLY_LOCK_KEY, token)
            except Exception:
                pass


def _skipped_sip_usernames():
    return list(get_users_excluded_from_pjsip().values_list("username", flat=True))


class ConfigPreviewView(APIView):
    """GET-only dry-run: same content as the admin's GET preview, no
    filesystem writes, no AMI. Superuser only."""

    permission_classes = [IsSuperUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="Generated config file contents.")},
        summary="Preview generated Asterisk config files (dry-run)",
        tags=["config"],
    )
    def get(self, request):
        admin_view = AdminApplyChangesView()
        cfgfiles = admin_view._build_cfgfiles()
        files = {os.path.basename(path): content for path, content in cfgfiles.items()}
        return Response(
            {
                "files": files,
                "skipped_sip_users": _skipped_sip_usernames(),
            }
        )


class ConfigApplyView(APIView):
    """Write configs (with backup) and reload Asterisk. Superuser only.

    mode=soft -> module/AEL reload (keeps active calls).
    mode=hard -> 'core restart now' (drops every active call).
    """

    permission_classes = [IsSuperUser]

    @extend_schema(
        request=ApplyChangesSerializer,
        responses={
            200: OpenApiResponse(description="Configs applied."),
            400: OpenApiResponse(description="Invalid request body."),
            409: OpenApiResponse(description="Another apply is already in progress."),
            500: OpenApiResponse(description="Applying the configuration failed."),
        },
        summary="Apply generated configs and reload Asterisk",
        tags=["config"],
    )
    def post(self, request):
        serializer = ApplyChangesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode = serializer.validated_data["mode"]

        with _apply_lock():
            admin_view = AdminApplyChangesView()
            cfgfiles = admin_view._build_cfgfiles()
            try:
                changed = admin_view.apply_changes(cfgfiles)
                reloaded = False
                if settings.DEVMODE != settings.DEVMODE_WITHOUT_ASTERISK:
                    with AsteriskManagementInterface() as ami:
                        if mode == "soft":
                            ami.soft_reload()
                        else:
                            ami.restart()
                    reloaded = True
            except Exception as e:
                # Covers both a failed apply_changes() and a failed AMI
                # reload — configs may already be written to disk in the
                # latter case, but the caller must still see a failure, not
                # a silently-swallowed one.
                return Response(
                    {"detail": f"An error occurred: {e}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        return Response(
            {
                "mode": mode,
                "changed_files": changed,
                "reloaded": reloaded,
                "skipped_sip_users": _skipped_sip_usernames(),
            }
        )
