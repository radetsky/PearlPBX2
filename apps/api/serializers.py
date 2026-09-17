import ipaddress
import random
import re

from django.conf import settings

from rest_framework import serializers
from rest_framework.validators import UniqueValidator, UniqueTogetherValidator
from drf_spectacular.utils import extend_schema_field

from apps.api.models import CustomListNames, CustomListEntries
from apps.provision.models import PhoneDevice
from core.models import (
    Blacklist,
    Whitelist,
    Contact,
    SIPUser,
    SIPTransport,
    SIPPeer,
    RoutingTable,
    RoutingRecord,
    TrunkGroup,
    DialplanContext,
    DialplanExtension,
    DialplanMacro,
    Queue,
    QueueMember,
)
from core.validators import (
    validate_asterisk_interface,
    validate_alphanumeric,
    validate_sip_username,
    validate_mac_address,
    min3len,
)


def _reject_line_breaks(value):
    """Guard against values interpolated into a single pjsip.conf comment line."""
    if value and re.search(r"[\r\n]", value):
        raise serializers.ValidationError("Must not contain line breaks.")
    return value


class HideSensitiveInListMixin:
    """Null out `sensitive_fields` in the `list` action's response only.

    A GET on the detail route, or the object returned by POST/PATCH, still
    includes the real value — this only keeps credentials out of a bulk,
    paginated dump. Requires the view to set `self.action` (true for any
    GenericViewSet/ModelViewSet), passed through via serializer context.
    """

    sensitive_fields: list[str] = []

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        view = self.context.get("view")
        if getattr(view, "action", None) == "list":
            for field in self.sensitive_fields:
                if field in ret:
                    ret[field] = None
        return ret


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


class SIPUserSerializer(HideSensitiveInListMixin, serializers.ModelSerializer):
    """A SIP extension. Saving here only updates the database — changes reach
    Asterisk after a superuser runs "Apply Changes" in the admin.

    `secret`/`md5_cred` are `null` in the list response — see them via GET
    on the detail route, or in the create/update response.
    """

    sensitive_fields = ["secret", "md5_cred"]

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


class SIPTransportSerializer(HideSensitiveInListMixin, serializers.ModelSerializer):
    """A PJSIP transport. Saving here only updates the database — changes reach
    Asterisk after a superuser runs "Apply Changes" in the admin.

    `cert_file`/`priv_key_file`/`ca_list_file` hold PEM contents, not paths —
    they are written to disk under the Asterisk certificate directory only
    when "Apply Changes" runs, and only for `protocol="tls"`.

    `priv_key_file` is `null` in the list response — see it via GET on the
    detail route, or in the create/update response.
    """

    sensitive_fields = ["priv_key_file"]

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


class SIPPeerSerializer(HideSensitiveInListMixin, serializers.ModelSerializer):
    """A SIP trunk/uplink. Saving here only updates the database — changes
    reach Asterisk after a superuser runs "Apply Changes" in the admin.

    `secret`/`md5_cred` are `null` in the list response — see them via GET
    on the detail route, or in the create/update response.
    """

    sensitive_fields = ["secret", "md5_cred"]

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


class RoutingRecordSerializer(serializers.ModelSerializer):
    """A prefix-based routing rule within a `RoutingTable`
    (core.conf.make_routing_tables() emits one `goto` per record, sorted by
    Asterisk pattern specificity).
    """

    context_name = serializers.CharField(source="context.name", read_only=True)
    routing_table_name = serializers.CharField(source="routing_table.name", read_only=True)

    class Meta:
        model = RoutingRecord
        fields = [
            "id",
            "name",
            "prefix",
            "context",
            "context_name",
            "routing_table",
            "routing_table_name",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            # Both FKs are nullable in the DB but a null value here breaks the
            # generated dialplan — core.conf.make_routing_tables() interpolates
            # `context` verbatim into `goto {context},${EXTEN},1;` with no null
            # guard (a null context literally emits "goto None,..."), and a
            # record with no routing_table never appears in any table's block.
            "context": {"required": True, "allow_null": False},
            "routing_table": {"required": True, "allow_null": False},
        }


class DialplanContextSerializer(serializers.ModelSerializer):
    """A dialplan context (core.conf.make_dialplan_contexts()). `name`
    shares a naming namespace with RoutingTable — the two must not collide.
    """

    extensions_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = DialplanContext
        fields = [
            "id",
            "name",
            "description",
            "extensions_count",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]

    def validate_name(self, value):
        if RoutingTable.objects.filter(name=value).exists():
            raise serializers.ValidationError(
                f'Context name "{value}" already exists in RoutingTable.'
            )
        if (
            self.instance
            and self.instance.name in DialplanContext.RESERVED_NAMES
            and self.instance.name != value
        ):
            raise serializers.ValidationError(
                f'Cannot rename the auto-generated "{self.instance.name}" context.'
            )
        return value

    def validate_description(self, value):
        return _reject_line_breaks(value)


class DialplanExtensionSerializer(serializers.ModelSerializer):
    """A dialplan extension inside a DialplanContext
    (core.conf.make_dialplan_contexts()). `dialplan` is checked against
    Asterisk AEL syntax and the current set of DialplanMacro names by
    core.validators.validate_dialplan_field — create a macro before an
    extension that calls it.
    """

    context_name = serializers.CharField(source="context.name", read_only=True)

    class Meta:
        model = DialplanExtension
        fields = [
            "id",
            "context",
            "context_name",
            "ext",
            "dialplan",
            "description",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            # Nullable in the DB, but core.conf.make_dialplan_contexts() only
            # emits extensions grouped under a context — one with no context
            # never reaches extensions.ael.
            "context": {"required": True, "allow_null": False},
        }
        # `context` is null=True at the model level, so DRF's automatic
        # UniqueConstraint("context", "ext") handling would otherwise inject
        # default=None for it (to make unique-together validation work with
        # a missing field), which conflicts with the required=True above.
        # Declaring the validator explicitly opts out of that auto-injection
        # — same escape hatch QueueMemberSerializer uses for (queue, interface).
        validators = [
            UniqueTogetherValidator(
                queryset=DialplanExtension.objects.all(), fields=["context", "ext"]
            )
        ]

    def validate_context(self, value):
        if value.name in DialplanContext.RESERVED_NAMES:
            raise serializers.ValidationError(
                "This context is generated live from SIP users "
                "(core.conf.make_local_users_context()); extensions stored "
                "here are never emitted into extensions.ael."
            )
        return value

    def validate_description(self, value):
        return _reject_line_breaks(value)


class DialplanMacroSerializer(serializers.ModelSerializer):
    """A dialplan macro (core.conf.make_dialplan_macros()), called from
    extension bodies as `&name();`. `name` is looked up as literal AEL macro
    call text — renaming or deleting a macro still called that way is
    rejected (400/409) instead of silently breaking the generated dialplan.
    """

    class Meta:
        model = DialplanMacro
        fields = [
            "id",
            "name",
            "description",
            "macro",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]

    def validate_name(self, value):
        if self.instance and self.instance.name != value:
            refs = DialplanMacro.find_dialplan_references(self.instance.name)
            if refs:
                raise serializers.ValidationError(
                    f"Cannot rename: still referenced by dialplan: {', '.join(refs)}."
                )
        return value

    def validate_description(self, value):
        return _reject_line_breaks(value)


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


class PhoneDeviceSerializer(serializers.ModelSerializer):
    """A provisioned phone (or softphone/WebRTC client). Saving here only
    updates the database — a config file is written to the TFTP directory
    only via the `provision` action, or the admin's "Apply configurations"
    action.

    `sip_user` is optional: a device with none assigned is a normal,
    not-yet-configured state (see PhoneDeviceAdmin's "No SIP User" status).
    """

    mac_address = serializers.CharField(max_length=17)
    sip_user_username = serializers.SerializerMethodField()

    class Meta:
        model = PhoneDevice
        fields = [
            "id",
            "telephone_type",
            "mac_address",
            "sip_user",
            "sip_user_username",
            "sip_server",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            "sip_server": {"required": False, "allow_blank": True},
        }

    def validate_mac_address(self, value):
        # A field-level `validators=[...]` entry can only reject a value, not
        # transform it — normalization has to happen here instead, before the
        # uniqueness check below (a bare UniqueValidator would otherwise check
        # the pre-normalization string, letting a differently-formatted
        # duplicate through to hit the DB's unique constraint as a 409 instead
        # of this 400).
        normalized = validate_mac_address(value)
        qs = PhoneDevice.objects.filter(mac_address=normalized)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A phone device with this MAC address already exists."
            )
        return normalized

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_sip_user_username(self, obj):
        return obj.sip_user.username if obj.sip_user else None


class QueueSerializer(serializers.ModelSerializer):
    """A call queue (app_queue). `name` is looked up by Asterisk's app_queue
    from a literal `Queue(<name>,...)` AEL app-call embedded in dialplan
    text, so renaming or deleting a queue still referenced there is
    rejected (see Queue.find_dialplan_references()).

    Saving here only updates the database; changes reach Asterisk after a
    superuser runs "Apply Changes" in the admin.
    """

    music_class_name = serializers.CharField(source="music_class.name", read_only=True)
    queue_announcement_name = serializers.CharField(
        source="queue_announcement.name", read_only=True
    )
    defaultrule_name = serializers.SerializerMethodField()
    # default=0 covers create(): the freshly saved instance isn't re-fetched
    # through the view's annotated queryset, so the annotation is absent —
    # correctly so, since nothing can reference a queue that was just created.
    members_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Queue
        fields = [
            "id",
            "name",
            "music_class",
            "music_class_name",
            "announce",
            "queue_announce",
            "strategy",
            "service_level",
            "context",
            "maxlen",
            "timeout",
            "retry",
            "timeoutpriority",
            "weight",
            "wrapuptime",
            "autofill",
            "autopause",
            "autopausedelay",
            "reportholdtime",
            "setinterfacevar",
            "setqueueentryvar",
            "setqueuevar",
            "announce_frequency",
            "min_announce_frequency",
            "periodic_announce_frequency",
            "random_periodic_announce",
            "relative_periodic_announce",
            "announce_holdtime",
            "announce_position",
            "announce_to_first_user",
            "announce_position_limit",
            "announce_round_seconds",
            "announce_position_only_up",
            "queue_announcement",
            "queue_announcement_name",
            "periodic_announce",
            "monitor_format",
            "joinempty",
            "leavewhenempty",
            "ringinuse",
            "timeoutrestart",
            "defaultrule",
            "defaultrule_name",
            "members_count",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            # Nullable/blank in the DB, but core.conf._make_single_queue_config()
            # interpolates it verbatim with no null guard: f"strategy={queue.strategy}"
            # — an empty value would literally emit "strategy=None" into queues.conf.
            "strategy": {"required": True, "allow_null": False, "allow_blank": False},
        }

    def validate_name(self, value):
        if self.instance and self.instance.name != value:
            refs = Queue.find_dialplan_references(self.instance.name)
            if refs:
                raise serializers.ValidationError(
                    f"Cannot rename: still referenced by dialplan: {', '.join(refs)}."
                )
        return value

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_defaultrule_name(self, obj):
        return obj.defaultrule.name if obj.defaultrule else None


class QueueMemberSerializer(serializers.ModelSerializer):
    """A static queue member (core.conf._make_single_queue_config() emits one
    `member =>` line per row). Distinct from GET /api/v1/queues/members/ and
    POST /api/v1/queues/members/pause/, which read/write Asterisk's live AMI
    state instead of this DB configuration.
    """

    interface = serializers.CharField(
        max_length=64,
        validators=[validate_asterisk_interface],
        help_text="Queue member interface, e.g. 'PJSIP/101'.",
    )
    queue_name = serializers.CharField(source="queue.name", read_only=True)

    class Meta:
        model = QueueMember
        fields = [
            "id",
            "queue",
            "queue_name",
            "interface",
            "penalty",
            "member_name",
            "state_interface",
            "ringinuse",
            "wrapuptime",
            "created_at",
            "created_by",
            "modified_at",
            "modified_by",
        ]
        read_only_fields = ["id", "created_at", "created_by", "modified_at", "modified_by"]
        extra_kwargs = {
            # Nullable in the DB, but the generated "member => ..." line has
            # no null guard for this field — a null would render as the
            # literal word "None" rather than an empty column.
            "member_name": {
                "required": False,
                "allow_blank": True,
                "allow_null": False,
                "default": "",
            },
        }
        validators = [
            UniqueTogetherValidator(
                queryset=QueueMember.objects.all(), fields=["queue", "interface"]
            )
        ]


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
