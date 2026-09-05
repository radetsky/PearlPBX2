import random

from django.conf import settings

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_spectacular.utils import extend_schema_field

from apps.api.models import CustomListNames, CustomListEntries
from core.models import Blacklist, Whitelist, Contact, SIPUser
from core.validators import (
    validate_asterisk_interface,
    validate_alphanumeric,
    min3len,
)


class CustomListNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomListNames
        fields = ["id", "name"]
        read_only_fields = ["id"]


class CustomListEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomListEntries
        fields = ["id", "callerid", "destination", "reason", "expiration_date"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "destination": {"required": False, "allow_blank": True, "default": ""},
            "reason": {"required": False, "allow_blank": True, "default": ""},
            "expiration_date": {"required": False, "allow_null": True},
        }


class _CallerListSerializer(serializers.ModelSerializer):
    """Shared base for Blacklist/Whitelist (identical fields)."""

    class Meta:
        fields = ["id", "callerid", "destination", "reason", "expiration_date"]
        read_only_fields = ["id"]
        validators = []
        extra_kwargs = {
            "destination": {"required": False, "allow_blank": True, "default": ""},
            "reason": {"required": False, "allow_blank": True, "default": ""},
            "expiration_date": {"required": False, "allow_null": True},
        }


class BlacklistSerializer(_CallerListSerializer):
    class Meta(_CallerListSerializer.Meta):
        model = Blacklist


class WhitelistSerializer(_CallerListSerializer):
    class Meta(_CallerListSerializer.Meta):
        model = Whitelist


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ["id", "callerid", "name"]
        read_only_fields = ["id"]
        extra_kwargs = {
            "callerid": {"validators": []},
        }


class SIPUserSerializer(serializers.ModelSerializer):
    """A SIP extension. Saving here only updates the database — changes reach
    Asterisk after a superuser runs "Apply Changes" in the admin.
    """

    name = serializers.CharField(max_length=64, validators=[min3len])
    username = serializers.CharField(
        max_length=32,
        validators=[
            validate_alphanumeric,
            min3len,
            UniqueValidator(queryset=SIPUser.objects.all()),
        ],
    )
    extension = serializers.CharField(
        max_length=32,
        validators=[
            validate_alphanumeric,
            UniqueValidator(queryset=SIPUser.objects.all()),
        ],
    )
    transport_name = serializers.CharField(source="transport.name", read_only=True)
    routing_table_name = serializers.CharField(source="routing_table.name", read_only=True)
    pjsip_endpoint = serializers.CharField(source="standard_pjsip_user", read_only=True)
    is_webrtc = serializers.SerializerMethodField()
    realm = serializers.SerializerMethodField()
    md5_cred = serializers.SerializerMethodField()

    class Meta:
        model = SIPUser
        fields = [
            "id",
            "name",
            "username",
            "secret",
            "transport",
            "transport_name",
            "nat",
            "extension",
            "routing_table",
            "routing_table_name",
            "auth_type",
            "custom_extension",
            "custom_settings",
            "custom_auth_settings",
            "custom_aor_settings",
            "pjsip_endpoint",
            "is_webrtc",
            "realm",
            "md5_cred",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            # Both FKs are nullable in the DB (legacy rows) but a null value
            # here silently drops the user from generated pjsip.conf — see
            # core.conf.get_users_excluded_from_pjsip() — so the API requires
            # them, matching SIPUserForm.
            "transport": {"required": True, "allow_null": False},
            "routing_table": {"required": True, "allow_null": False},
        }

    @staticmethod
    def _if_transport(obj, value_fn):
        """obj.realm/obj.md5_cred raise if obj.transport is None (core.models.SIPUser)."""
        return value_fn(obj) if obj.transport else None

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_is_webrtc(self, obj):
        return self._if_transport(obj, lambda o: o.transport.protocol == "wss")

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_realm(self, obj):
        return self._if_transport(obj, lambda o: o.realm)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_md5_cred(self, obj):
        return self._if_transport(obj, lambda o: o.md5_cred)


class _CallOriginationFieldsSerializer(serializers.Serializer):
    """Fields shared by every endpoint that originates one or more AMI calls."""

    callerid = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        help_text="Caller ID applied to the call, format 'name<number>', e.g. '380443333333<0675653380>'.",
    )
    timeout_ms = serializers.IntegerField(
        default=30000,
        min_value=1000,
        max_value=120000,
        help_text="Max time to wait for the call to answer, in milliseconds.",
    )


class OriginateSerializer(_CallOriginationFieldsSerializer):
    channel = serializers.CharField(
        max_length=256,
        help_text="First leg to dial, e.g. 'Local/0503856087@default' or 'PJSIP/101'.",
    )
    exten = serializers.CharField(
        max_length=128,
        help_text="Extension/number the first leg is connected to, e.g. '0675653380'.",
    )
    context = serializers.CharField(
        max_length=128,
        default="default",
        help_text="Dialplan context. Defaults to 'default'.",
    )
    priority = serializers.IntegerField(
        default=1, min_value=1, help_text="Dialplan priority."
    )
    variable = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        help_text='Channel variables, e.g. {"userId": "0"}.',
    )

    def to_ami_kwargs(self):
        data = self.validated_data
        kwargs = {
            "channel": data["channel"],
            "exten": data["exten"],
            "context": data["context"],
            "priority": data["priority"],
            "timeout_ms": data["timeout_ms"],
            "variables": data.get("variable") or {},
        }
        callerid = data.get("callerid")
        if callerid:
            kwargs["callerid"] = callerid
        return kwargs


class ConferenceSerializer(_CallOriginationFieldsSerializer):
    parties = serializers.ListField(
        child=serializers.CharField(max_length=256, allow_blank=False),
        min_length=2,
        help_text=(
            "Channels to originate into the same conference room, e.g. "
            '["PJSIP/101", "PJSIP/0504139380@mega-provider", "Local/2222@internal"].'
        ),
    )
    room = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text=(
            "Conference room number. If omitted, a new one is generated "
            "and returned in the response."
        ),
    )
    context = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        help_text=(
            "Dialplan context that lands each leg into ConfBridge. "
            "Defaults to settings.PEARLPBX_CONFERENCE_CONTEXT."
        ),
    )

    @staticmethod
    def generate_room() -> str:
        # Numeric room number matching CONFERENCE_ROOM_EXTENSION_PATTERN in core.conf.
        return str(random.randint(100_000_000, 999_999_999))

    def to_originate_kwargs_list(self) -> tuple[str, list[dict]]:
        data = self.validated_data
        room = data.get("room") or self.generate_room()
        context = data.get("context") or settings.PEARLPBX_CONFERENCE_CONTEXT
        callerid = data.get("callerid")

        kwargs_list = []
        for channel in data["parties"]:
            kwargs = {
                "channel": channel,
                "exten": room,
                "context": context,
                "priority": 1,
                "timeout_ms": data["timeout_ms"],
                "async_originate": True,
            }
            if callerid:
                kwargs["callerid"] = callerid
            kwargs_list.append(kwargs)

        return room, kwargs_list


class QueueMemberPauseSerializer(serializers.Serializer):
    interface = serializers.CharField(
        max_length=128,
        validators=[validate_asterisk_interface],
        help_text="Queue member interface, e.g. 'PJSIP/101'.",
    )
    paused = serializers.BooleanField(help_text="True to pause, false to unpause.")
    queue = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text=(
            "Limit the pause/unpause to one queue. Omitted, it applies to the "
            "member in every queue it belongs to."
        ),
    )


class QueueMemberStatusSerializer(serializers.Serializer):
    """Read-only shape of a queue member returned by the members list endpoint."""

    queue = serializers.CharField()
    name = serializers.CharField()
    location = serializers.CharField()
    state_interface = serializers.CharField()
    membership = serializers.CharField()
    penalty = serializers.IntegerField()
    calls_taken = serializers.IntegerField()
    last_call = serializers.IntegerField()
    in_call = serializers.BooleanField()
    status = serializers.CharField(help_text="Raw AMI device status code.")
    paused = serializers.BooleanField()

    @staticmethod
    def from_ami_event(event) -> dict:
        """Map a raw AMI QueueMember event into this serializer's field shape."""
        keys = event.keys

        def _int(name):
            try:
                return int(keys.get(name, 0))
            except (TypeError, ValueError):
                return 0

        return {
            "queue": keys.get("Queue", ""),
            "name": keys.get("Name", ""),
            "location": keys.get("Location", ""),
            "state_interface": keys.get("StateInterface", ""),
            "membership": keys.get("Membership", ""),
            "penalty": _int("Penalty"),
            "calls_taken": _int("CallsTaken"),
            "last_call": _int("LastCall"),
            "in_call": keys.get("InCall") == "1",
            "status": keys.get("Status", ""),
            "paused": keys.get("Paused") == "1",
        }


class QueueMemberListSerializer(serializers.Serializer):
    """Response shape of GET /api/v1/queues/members/."""

    members = QueueMemberStatusSerializer(many=True)
