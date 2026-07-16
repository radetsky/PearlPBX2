from typing import Optional

from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    SIPTransport,
    SIPUser,
    SIPPeer,
    DialplanContext,
    DialplanExtension,
    DialplanMacro,
    Settings,
    MusicOnHoldPlaylistEntry,
    MusicOnHold,
    CallQueueGlobalSettings,
    Queue,
    QueueMember,
    QueueAnnouncements,
    QueueRule,
    PenaltyChange,
    ConfigurationFile,
    BinaryFile,
    SystemConfiguration,
    TrunkGroup,
    RoutingTable,
    RoutingRecord,
    Blacklist,
    Whitelist,
    Contact,
    ManagerUsers,
    SoundFile,
)
from .forms import (
    RoutingTableAdminForm,
    SIPUserForm,
    SIPPeerForm,
    DialplanExtensionForm,
    DialplanContextAdminForm,
    ConfigurationFileForm,
    QueueAdminForm,
    DEFAULT_QUEUE_MEMBER_PENALTY,
)

# TODO: Use some template, edit and use UIKIT accordion to make admin forms better readable
# Right here we just can hide fieldsets
# [ custom_extension, custom_settings, custom_auth_settings,custom_aor_settings ]


class SIPUserAdmin(admin.ModelAdmin):
    form = SIPUserForm
    list_display = ("name", "username", "extension")
    ordering = ["name", "username", "extension"]
    search_fields = ["name", "username", "extension"]


class SIPPeerAdmin(admin.ModelAdmin):
    form = SIPPeerForm
    list_display = ("name", "description")
    ordering = ["name", "description"]
    search_fields = ["name", "description"]

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)

    fieldsets = [
        (_("Generic"), {"fields": ["name", "description", "transport", "routing_table"]}),
        (
            _("Authentication"),
            {"fields": ["username", "contact_user", "auth_type", "secret", "custom_auth_settings"]},
        ),
        (
            _("Connection"),
            {
                "fields": [
                    "registration_uri",
                    "contact_uri",
                    "match_hosts",
                ],
                "description": _(
                    "registration_uri — where to register; "
                    "contact_uri — where to send calls; "
                    "match_hosts — comma-separated IPs/hostnames to match incoming calls"
                ),
            },
        ),
        (
            _("Registration"),
            {"fields": ["registrationHere", "registrationThere"]},
        ),
        (
            _("Advanced"),
            {
                "fields": ["nat", "custom_aor_settings"],
                "classes": ["collapse"],
            },
        ),
    ]


class SIPTransportAdmin(admin.ModelAdmin):
    fieldsets = [
        (_("Generic"), {"fields": ["description", "name"]}),
        (
            _("Network settings"),
            {
                "fields": [
                    "protocol",
                    "bind",
                    "local_nets",
                    "external_media_address",
                    "external_signaling_address",
                ]
            },
        ),
        (
            _("TLS Settings (only if TLS protocol is used)"),
            {"fields": ["method", "verify_server", "allow_reload", "cert_file", "priv_key_file", "ca_list_file"]},
        ),
    ]
    list_display = ("name", "description")
    ordering = ["name", "description"]


class DialplanExtensionInlineAdmin(admin.TabularInline):
    min_num: Optional[int] = 1
    extra: Optional[int] = 0
    model = DialplanExtension

    form = DialplanExtensionForm
    fields = ["context", "ext", "dialplan", "description"]
    ordering = ["ext"]


class DialplanContextAdmin(admin.ModelAdmin):
    form = DialplanContextAdminForm
    fields = ["name", "description"]
    list_display = ("name", "description")
    ordering = ["name", "description"]
    search_fields = ["name", "description"]
    inlines = [DialplanExtensionInlineAdmin]


class DialplanExtensionAdmin(admin.ModelAdmin):
    form = DialplanExtensionForm
    fields = ["context", "ext", "dialplan", "description"]
    list_display = ("context_name", "ext", "description")
    ordering = ["context", "ext"]
    search_fields = ["ext", "dialplan", "description"]


class DialplanMacroAdmin(admin.ModelAdmin):
    fields = ["name", "description", "macro"]
    list_display = ("name", "description")
    ordering = ["name", "description"]
    search_fields = ["name", "description", "macro"]


class MusicOnHoldPlaylistEntryAdmin(admin.ModelAdmin):
    fields = ["moh_class", "file", "url"]
    list_display = ("moh_class", "file", "url")
    ordering = ["moh_class", "file", "url"]
    search_fields = ["moh_class", "file", "url"]


class MusicOnHoldPlaylistEntryInlineAdmin(admin.TabularInline):
    min_num: Optional[int] = 1
    extra: Optional[int] = 0
    model = MusicOnHoldPlaylistEntry

    fields = ["file", "url", "moh_class"]
    ordering = ["file", "url"]
    search_fields = ["file", "url"]


class MusicOnHoldAdmin(admin.ModelAdmin):
    fields = ["name", "mode", "directory", "sort"]
    list_display = ("name", "directory")
    ordering = ["name"]
    search_fields = ["name"]
    inlines = [MusicOnHoldPlaylistEntryInlineAdmin]


class RoutingRecordAdmin(admin.ModelAdmin):
    fields = ["prefix", "name", "context", "routing_table"]
    list_display = ("prefix", "name", "context", "routing_table")
    list_filter = [
        "routing_table",
        "context",
        ("routing_table", admin.RelatedOnlyFieldListFilter),
    ]
    ordering = ["prefix", "name"]
    # Пошук по пов'язаних об'єктах
    search_fields = ["prefix", "name", "context__name"]
    list_per_page = 50  # Пагінація


class RoutingRecordInlineAdmin(admin.TabularInline):
    model = RoutingRecord
    min_num = 1
    extra = 0

    fields = ["name", "prefix", "context"]
    ordering = ["name", "prefix"]

    autocomplete_fields = ["context"]

    verbose_name = _("Routing Record")
    verbose_name_plural = _("Routing Records")


class RoutingTableAdmin(admin.ModelAdmin):
    form = RoutingTableAdminForm
    fields = ["name"]
    ordering = ["name"]
    search_fields = ["name"]
    inlines = [RoutingRecordInlineAdmin]


class PenaltyChangeInlineAdmin(admin.TabularInline):
    min_num: Optional[int] = 1
    extra: Optional[int] = 0
    model = PenaltyChange

    fields = ["seconds", "max_penalty", "min_penalty", "raise_penalty", "order"]
    ordering = ["rule", "seconds"]
    search_fields = [
        "rule__name",
        "seconds",
        "max_penalty",
        "min_penalty",
        "raise_penalty",
        "order",
    ]


class QueueRuleAdmin(admin.ModelAdmin):
    fields = ["name", "description"]
    ordering = ["name", "description"]
    search_fields = ["name", "description"]
    inlines = [PenaltyChangeInlineAdmin]


class ConfigurationFileAdmin(admin.ModelAdmin):
    form = ConfigurationFileForm
    fields = ["name", "description", "path", "content"]
    list_display = ("name", "version", "created", "description")
    ordering = ["name", "path"]
    search_fields = ["name", "description", "content"]

    def save_model(self, request, obj, form, change):
        last_instance = (
            ConfigurationFile.objects.filter(name=obj.name).order_by("-version").first()
        )
        if not last_instance:
            obj.save()
            return
        if last_instance.content != obj.content:
            # Create new ConfigurationFile instance with incremented version
            obj.pk = None
            obj.version = last_instance.version + 1
            obj.created = timezone.now()
            obj.save()
        else:
            # Content unchanged: still persist name/description/path edits on the
            # existing row instead of silently discarding them.
            obj.save()
            messages.info(
                request,
                _(
                    "Content unchanged — no new version created; other field "
                    "edits were saved."
                ),
            )


class SoundFileAdmin(admin.ModelAdmin):
    fields = ("language", "name", "file")  # Language — перед file
    list_display = ("language", "name")
    search_fields = ("language", "name")


class QueueMemberAdmin(admin.ModelAdmin):
    list_display = ("member_name", "interface", "state_interface", "queue", "penalty")
    search_fields = ("member_name", "interface", "state_interface", "queue__name")
    ordering = ("member_name", "queue__name", "penalty")


class QueueMemberInlineAdmin(admin.TabularInline):
    model = QueueMember
    extra = 0
    min_num = 1
    fields = (
        "member_name",
        "interface",
        "state_interface",
        "penalty",
    )
    ordering = ("member_name",)


class QueueAdmin(admin.ModelAdmin):
    form = QueueAdminForm
    list_display = ["name", "defaultrule", "strategy"]
    search_fields = ["name"]
    ordering = ["name"]
    readonly_fields = ["rule_link"]
    inlines = [QueueMemberInlineAdmin]
    fieldsets = [
        (None, {"fields": ["name", "strategy", "music_class"]}),
        (
            _("Add Members"),
            {
                "fields": ["add_sip_users"],
                "description": _(
                    "Select SIP users to bulk-add as queue members. "
                    "Existing members are not changed. Use the inline below to adjust details."
                ),
            },
        ),
        (
            _("Queue Rules"),
            {
                "fields": ["defaultrule", "rule_link"],
                "description": _(
                    "Select a rule and click the link to edit its penalty changes."
                ),
            },
        ),
        (
            _("Timeouts"),
            {
                "fields": [
                    "timeout",
                    "retry",
                    "maxlen",
                    "wrapuptime",
                    "autopause",
                    "autopausedelay",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            _("Announcements"),
            {
                "fields": [
                    "announce",
                    "queue_announce",
                    "queue_announcement",
                    "announce_frequency",
                    "announce_holdtime",
                    "announce_position",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            _("Advanced"),
            {
                "fields": [
                    "context",
                    "service_level",
                    "weight",
                    "autofill",
                    "ringinuse",
                    "joinempty",
                    "leavewhenempty",
                    "monitor_format",
                    "timeoutpriority",
                    "timeoutrestart",
                    "reportholdtime",
                    "setinterfacevar",
                    "setqueueentryvar",
                    "setqueuevar",
                    "min_announce_frequency",
                    "periodic_announce_frequency",
                    "periodic_announce",
                    "random_periodic_announce",
                    "relative_periodic_announce",
                    "announce_to_first_user",
                    "announce_position_limit",
                    "announce_round_seconds",
                    "announce_position_only_up",
                ],
                "classes": ["collapse"],
            },
        ),
    ]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        queue = form.instance
        for sip_user in form.cleaned_data.get("add_sip_users", []):
            interface = f"PJSIP/{sip_user.username}"
            QueueMember.objects.get_or_create(
                queue=queue,
                interface=interface,
                defaults={
                    "member_name": sip_user.username,
                    "state_interface": interface,
                    "penalty": DEFAULT_QUEUE_MEMBER_PENALTY,
                },
            )

    @admin.display(description=_("Edit Rule"))
    def rule_link(self, obj):
        if not obj.defaultrule:
            add_url = reverse("admin:core_queuerule_add")
            return format_html(
                '<a href="{}" target="_blank">+ Create new rule</a>', add_url
            )
        edit_url = reverse("admin:core_queuerule_change", args=[obj.defaultrule.pk])
        list_url = reverse("admin:core_queuerule_changelist")
        return format_html(
            '<a href="{}" target="_blank">Edit "{}"</a> &nbsp;|&nbsp; <a href="{}" target="_blank">All rules</a>',
            edit_url,
            obj.defaultrule.name,
            list_url,
        )


admin.site.register(SIPUser, SIPUserAdmin)
admin.site.register(SIPPeer, SIPPeerAdmin)
admin.site.register(SIPTransport, SIPTransportAdmin)
admin.site.register(DialplanContext, DialplanContextAdmin)
admin.site.register(DialplanExtension, DialplanExtensionAdmin)
admin.site.register(DialplanMacro, DialplanMacroAdmin)
admin.site.register(Settings)
admin.site.register(MusicOnHoldPlaylistEntry, MusicOnHoldPlaylistEntryAdmin)
admin.site.register(MusicOnHold, MusicOnHoldAdmin)
admin.site.register(RoutingTable, RoutingTableAdmin)
admin.site.register(RoutingRecord, RoutingRecordAdmin)
admin.site.register(ConfigurationFile, ConfigurationFileAdmin)
admin.site.register(SoundFile, SoundFileAdmin)
admin.site.register(QueueRule, QueueRuleAdmin)
admin.site.register(Queue, QueueAdmin)
admin.site.register(QueueMember, QueueMemberAdmin)


class TrunkGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "peer_count"]
    search_fields = ["name"]
    ordering = ["name"]
    filter_horizontal = ["sip_peers"]

    @admin.display(description="SIP Peers")
    def peer_count(self, obj):
        return obj.sip_peers.count()


admin.site.register(QueueAnnouncements)
admin.site.register(CallQueueGlobalSettings)
admin.site.register(TrunkGroup, TrunkGroupAdmin)
admin.site.register(BinaryFile)
admin.site.register(SystemConfiguration)
admin.site.register(Blacklist)
admin.site.register(Whitelist)
admin.site.register(Contact)
admin.site.register(ManagerUsers)
