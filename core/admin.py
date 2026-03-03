from typing import Optional

from django.contrib import admin
from django.utils import timezone

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


class SIPTransportAdmin(admin.ModelAdmin):
    fieldsets = [
        ("Generic", {"fields": ["description", "name"]}),
        (
            "Network settings",
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
            "TLS Settings (only if TLS protocol is used)",
            {"fields": ["method", "cert_file", "priv_key_file", "ca_list_file"]},
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

    verbose_name = "Routing Record"
    verbose_name_plural = "Routing Records"


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
            # Create new ConfigirationFile instance with incremented version
            obj.pk = None
            obj.version = last_instance.version + 1
            obj.created = timezone.now()
            obj.save()


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
    list_display = ["name"]
    search_fields = ["name"]
    ordering = ["name"]

    inlines = [QueueMemberInlineAdmin]


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
