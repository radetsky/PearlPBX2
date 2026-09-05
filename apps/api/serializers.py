import ipaddress
import random
import re

from django.conf import settings

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from drf_spectacular.utils import extend_schema_field

from apps.api.models import CustomListNames, CustomListEntries
from core.models import (
    Blacklist,
    Whitelist,
    Contact,
    SIPUser,
    SIPTransport,
    SIPPeer,
    RoutingTable,
    TrunkGroup,
    DialplanContext,
)
from core.validators import (
    validate_asterisk_interface,
    validate_alphanumeric,
    validate_sip_username,
    min3len,
)


def _reject_line_breaks(value):
    """Guard against values interpolated into a single pjsip.conf comment line."""
    if value and re.search(r"[\r\n]", value):
        raise serializers.ValidationError("Must not contain line breaks.")
    return value


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

    def validate_name(self, value):
        # core.conf.py interpolates name verbatim into a callerid=/comment
        # line; a line break would let it inject a second pjsip.conf directive.
        return _reject_line_breaks(value)

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


class SIPTransportSerializer(serializers.ModelSerializer):
    """A PJSIP transport. Saving here only updates the database — changes reach
    Asterisk after a superuser runs "Apply Changes" in the admin.

    `cert_file`/`priv_key_file`/`ca_list_file` hold PEM contents, not paths —
    they are written to disk under the Asterisk certificate directory only
    when "Apply Changes" runs, and only for `protocol="tls"`.
    """

    local_nets = serializers.CharField(
        max_length=256,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Comma-separated CIDR networks, e.g. '10.0.0.0/16, 192.168.0.0/24'.",
    )
    has_tls_material = serializers.SerializerMethodField()
    # default=0 covers create(): the freshly saved instance isn't re-fetched
    # through the view's annotated queryset, so the annotation is absent —
    # correctly so, since nothing can reference a transport that was just created.
    sip_users_count = serializers.IntegerField(read_only=True, default=0)
    sip_peers_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = SIPTransport
        fields = [
            "id",
            "name",
            "description",
            "protocol",
            "bind",
            "local_nets",
            "external_media_address",
            "external_signaling_address",
            "method",
            "verify_server",
            "allow_reload",
            "cert_file",
            "priv_key_file",
            "ca_list_file",
            "has_tls_material",
            "sip_users_count",
            "sip_peers_count",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]

    def validate_description(self, value):
        return _reject_line_breaks(value)

    def validate_local_nets(self, value):
        # DB stores None for "no networks"; an API client sending "" would
        # otherwise emit a bare "local_net = " line into pjsip.conf
        # (core.conf.make_pjsip_conf_transports() only checks `is not None`).
        if not value or not value.strip():
            return None
        networks = [n.strip() for n in value.split(",") if n.strip()]
        for net in networks:
            try:
                ipaddress.ip_network(net, strict=False)
            except ValueError:
                raise serializers.ValidationError(
                    f"'{net}' is not a valid IP network, e.g. 10.0.0.0/16."
                )
        return ",".join(networks)

    @extend_schema_field(serializers.BooleanField())
    def get_has_tls_material(self, obj):
        return bool(
            (obj.cert_file or "").strip()
            or (obj.priv_key_file or "").strip()
            or (obj.ca_list_file or "").strip()
        )


class SIPPeerSerializer(serializers.ModelSerializer):
    """A SIP trunk/uplink. Saving here only updates the database — changes
    reach Asterisk after a superuser runs "Apply Changes" in the admin.
    """

    name = serializers.CharField(
        max_length=32,
        validators=[
            validate_alphanumeric,
            min3len,
            UniqueValidator(queryset=SIPPeer.objects.all()),
        ],
    )
    registration_here = serializers.BooleanField(source="registrationHere", required=False)
    registration_there = serializers.BooleanField(source="registrationThere", required=False)
    transport_name = serializers.CharField(source="transport.name", read_only=True)
    routing_table_name = serializers.CharField(source="routing_table.name", read_only=True)
    auth_realm = serializers.CharField(read_only=True)
    md5_cred = serializers.CharField(read_only=True)
    trunk_groups = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name"
    )

    class Meta:
        model = SIPPeer
        fields = [
            "id",
            "name",
            "description",
            "username",
            "contact_user",
            "auth_type",
            "secret",
            "transport",
            "transport_name",
            "routing_table",
            "routing_table_name",
            "registration_uri",
            "contact_uri",
            "match_hosts",
            "registration_here",
            "registration_there",
            "nat",
            "custom_auth_settings",
            "custom_aor_settings",
            "custom_identify_settings",
            "auth_realm",
            "md5_cred",
            "trunk_groups",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            # Both FKs are nullable in the DB but a null value here leaves the
            # peer half-generated (no [endpoint]/[aor] section, only [auth]) —
            # see core.conf.__section_trunk_endpoint()/__section_trunk_aor() —
            # so the API requires them, matching SIPPeerForm.
            "transport": {"required": True, "allow_null": False},
            "routing_table": {"required": True, "allow_null": False},
        }

    def validate_description(self, value):
        return _reject_line_breaks(value)

    def validate_username(self, value):
        validate_sip_username(value)
        return value

    def validate_contact_user(self, value):
        validate_sip_username(value)
        return value

    def validate(self, attrs):
        # A peer registering to the remote side with no registration_uri/username
        # is silently skipped by core.conf.__section_trunk_remote_registration()
        # instead of erroring — catch it here instead.
        registration_there = attrs.get(
            "registrationThere", getattr(self.instance, "registrationThere", False)
        )
        if registration_there:
            registration_uri = attrs.get(
                "registration_uri", getattr(self.instance, "registration_uri", "")
            )
            username = attrs.get("username", getattr(self.instance, "username", ""))
            errors = {}
            if not (registration_uri or "").strip():
                errors["registration_uri"] = (
                    "Required when registration_there is true."
                )
            if not (username or "").strip():
                errors["username"] = "Required when registration_there is true."
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class RoutingTableSerializer(serializers.ModelSerializer):
    """A routing table. Its name is both a PJSIP `context=` value and an AEL
    dialplan context name (core.conf.make_routing_tables()), so it shares a
    naming namespace with DialplanContext.
    """

    # RoutingTable.save() raises a plain django.core.exceptions.ValidationError
    # for this same collision (defense in depth for non-API callers) — that
    # class isn't handled by DRF, so without this check it would surface as a
    # 500 instead of a 400. See also the generic ValidationError->400 branch
    # in apps.api.exceptions.api_exception_handler.
    routing_records_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = RoutingTable
        fields = [
            "id",
            "name",
            "routing_records_count",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]

    def validate_name(self, value):
        if DialplanContext.objects.filter(name=value).exists():
            raise serializers.ValidationError(
                f'Context name "{value}" already exists in DialplanContext.'
            )
        return value


class TrunkGroupSerializer(serializers.ModelSerializer):
    """A trunk group (failover set of SIPPeers). `name` is looked up by
    services/fastagi/fastagi.py via raw SQL from a literal
    `dial-trunk-group,<name>,` AGI call embedded in dialplan text, so renaming
    or deleting a group still referenced there is rejected.
    """

    sip_peers = serializers.PrimaryKeyRelatedField(
        many=True, queryset=SIPPeer.objects.all(), required=False
    )
    sip_peer_names = serializers.SlugRelatedField(
        source="sip_peers", many=True, read_only=True, slug_field="name"
    )
    sip_peers_count = serializers.SerializerMethodField()

    class Meta:
        model = TrunkGroup
        fields = [
            "id",
            "name",
            "sip_peers",
            "sip_peer_names",
            "sip_peers_count",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]

    def validate_name(self, value):
        if self.instance and self.instance.name != value:
            refs = TrunkGroup.find_dialplan_references(self.instance.name)
            if refs:
                raise serializers.ValidationError(
                    f"Cannot rename: still referenced by dialplan: {', '.join(refs)}."
                )
        return value

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        # The queryset annotation (set on the pre-update instance) goes stale
        # the moment sip_peers is changed above — drop it so the getter below
        # recomputes a fresh count instead of returning the pre-update value.
        if hasattr(instance, "sip_peers_count"):
            del instance.sip_peers_count
        return instance

    @extend_schema_field(serializers.IntegerField())
    def get_sip_peers_count(self, obj):
        # The queryset annotation isn't present on the instance returned by
        # create() (a brand-new object, unlike SIPTransport/SIPPeer, can
        # already have members — they're set in the same request) — fall
        # back to a direct count so a just-created group reports correctly.
        if hasattr(obj, "sip_peers_count"):
            return obj.sip_peers_count
        return obj.sip_peers.count()


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


class ApplyChangesSerializer(serializers.Serializer):
    """Required, no implicit default — unlike the admin form, where anything
    other than the literal string "soft" silently means a hard restart.
    """

    mode = serializers.ChoiceField(
        choices=["soft", "hard"],
        help_text=(
            "'soft': module/AEL reload, keeps active calls. "
            "'hard': 'core restart now', drops every active call."
        ),
    )


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
