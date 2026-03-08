from django.db.models import Q, F
from django.db import models
import os
from uuid import uuid4

import django.db.models.deletion as deletion
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.validators import (
    MinValueValidator,
    MaxValueValidator,
    FileExtensionValidator,
)
from django.conf import settings
from django.contrib.auth.models import User

from collections.abc import Iterable
from typing import Optional

from hashlib import md5

from django.urls import reverse

from core.storages import MOHFileSystemStorage, SoundsFileSystemStorage
from core.utils import generate_32_char_password, generate_64_char_password
from core.validators import (
    validate_bind_ip,
    validate_asterisk_context,
    validate_asterisk_extension_prefix,
    validate_penalty_value,
)

import logging

logger = logging.getLogger(__name__)


class AuditFields(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    modified_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_modified",
    )

    class Meta:
        abstract = True


class SIPTransport(models.Model):
    PROTOCOL_CHOICES = [
        ("udp", "UDP"),
        ("tcp", "TCP"),
        ("tls", "TLS"),
        ("wss", "WSS"),
    ]

    METHOD_CHOICES = [
        ("default", "The default as defined by PJSIP. This is currently TLSv1"),
        ("tlsv1", "TLSv1"),
        ("tlsv1_1", "TLSv1.1"),
        ("tlsv1_2", "TLSv1.2"),
        ("sslv2", "SSLv2"),
        ("sslv3", "SSLv3"),
        ("sslv23", "SSLv2.3"),
    ]

    description = models.CharField(
        default="",
        max_length=64,
        help_text="Example: UDP + NAT for remote users",
        verbose_name="Description",
        blank=True,
    )
    name = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        default="",
        help_text="Example: transport-udp-nat",
        verbose_name="Name",
    )
    protocol = models.CharField(
        max_length=3, null=False, choices=PROTOCOL_CHOICES, default="udp", blank=False
    )

    bind = models.CharField(
        validators=[validate_bind_ip],
        default="0.0.0.0",
        null=False,
        blank=False,
        max_length=256,
    )
    local_nets = models.CharField(
        null=True,
        blank=True,
        max_length=256,
        verbose_name="local_net",
        help_text="List all local networks splitted by comma: 10.0.0.0/16, 192.168.0.0/24",
    )
    external_media_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="This is the external IP address to use in RTP handling",
        verbose_name="External RTP IP address",
    )
    external_signaling_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="This is much like the external_media_address setting, but for SIP signaling instead of RTP media.",
        verbose_name="External SIP IP address",
    )
    method = models.CharField(
        max_length=10,
        null=False,
        choices=METHOD_CHOICES,
        default="default",
        blank=False,
    )

    # Contents of files, not names. We will generate filenames later. It doesn't matter.
    # TODO: реализовать форму под них.
    cert_file = models.TextField(blank=True, null=False)
    priv_key_file = models.TextField(blank=True, null=False)
    ca_list_file = models.TextField(blank=True, null=False)

    # various TLS specific options below:
    # cipher - do not use in UI "until it sleeps". Too many values. Users usually do not know it.

    class Meta:
        verbose_name_plural = "01. SIP Transports"


class DialplanContext(models.Model):
    name = models.CharField(
        max_length=80,
        unique=True,
        null=False,
        blank=False,
        verbose_name="Context name",
        help_text="Unique name for the context or routing tables, use latin symbols, digits and underscores",
        validators=[validate_asterisk_context],
    )
    description = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="Context description",
        help_text="Use latin symbols, digits and undercore to describe",
    )

    class Meta:
        db_table = "dialplan_contexts"
        verbose_name_plural = "04. Dialplan contexts"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if (
            RoutingTable.objects.filter(name=self.name)
            .exclude(pk=self.pk if self.pk else None)
            .exists()
        ):
            raise ValidationError(
                f'Context name "{self.name}" already exists in RoutingTable'
            )
        super().save(*args, **kwargs)

    @staticmethod
    def getUsersOrCreateUsers():
        # Find default PEARLPBX-Users context
        try:
            default_context = DialplanContext.objects.get(
                name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD
            )
        except DialplanContext.DoesNotExist:
            default_context = DialplanContext.objects.create(
                name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD,
                description="Default local users context",
            )

        return default_context


class RoutingTable(models.Model):
    name = models.CharField(
        max_length=80,
        unique=True,
        verbose_name="Routing table name",
        help_text="Unique name for the routing table and dialplan context, use latin symbols, digits and underscores",
        validators=[validate_asterisk_context],
    )

    class Meta:
        verbose_name_plural = "15. Routing Tables"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if (
            DialplanContext.objects.filter(name=self.name)
            .exclude(pk=self.pk if self.pk else None)
            .exists()
        ):
            raise ValidationError(
                f'Context name "{self.name}" already exists in DialplanContext'
            )
        super().save(*args, **kwargs)

    @staticmethod
    def getDefaultOrCreateDefault():
        # Find default PEARLPBX routing table
        try:
            default_routing_table = RoutingTable.objects.get(
                name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE
            )
        except RoutingTable.DoesNotExist:
            default_routing_table = RoutingTable.objects.create(
                name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE
            )

        return default_routing_table


class SIPUser(models.Model):
    AUTHTYPE_CHOICES = [
        ("userpass", "Plaintext"),
        ("md5", "MD5"),
    ]

    name = models.CharField(
        default="",
        max_length=64,
        blank=False,
        help_text="Full name of user, description of connection",
        verbose_name="Name",
    )
    username = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        help_text="Username: 3-32 characters",
        verbose_name="Username",
    )
    secret = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        help_text="Password for the connection",
        verbose_name="Password",
    )
    transport = models.ForeignKey(
        SIPTransport,
        related_name="sip_user_transport",
        on_delete=deletion.PROTECT,
        null=True,
        blank=False,
    )
    nat = models.BooleanField(
        default=False,
        help_text="Enable NAT traversal for this peer",
        verbose_name="NAT",
    )
    extension = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=False,
        help_text="Easy way to setup internal extension for the user",
        verbose_name="Extension",
    )
    routing_table = models.ForeignKey(
        RoutingTable,
        related_name="sip_user_routing_table",
        on_delete=deletion.PROTECT,
        null=True,
        blank=True,
    )
    auth_type = models.CharField(
        max_length=32,
        unique=False,
        null=True,
        blank=True,
        choices=AUTHTYPE_CHOICES,
        default="userpass",
        help_text="Type of authentication",
        verbose_name="Auth type",
    )
    allowed_extension = models.CharField(
        max_length=32,
        unique=False,
        null=True,
        blank=True,
        default="",
        help_text="Only one allowed extension for the user",
        verbose_name="Allowed extension",
    )
    custom_settings = models.TextField(
        null=True,
        blank=False,
        default="",
        help_text="Custom user settings",
        verbose_name="Settings",
    )
    custom_auth_settings = models.TextField(
        null=True,
        blank=False,
        default="",
        help_text="Custom user [auth] section",
        verbose_name="Auth Settings",
    )
    custom_aor_settings = models.TextField(
        null=True,
        blank=False,
        default="",
        help_text="Custom user [aor] section",
        verbose_name="AOR Settings",
    )
    custom_extension = models.TextField(
        null=True,
        blank=False,
        default="",
        help_text="Custom user extension section for incoming calls",
        verbose_name="Extension Settings",
    )
    # Here we are linking SIP Users to Django Users. Many SIP Users to Django one.
    django_user = models.ForeignKey(
        User,
        related_name="sip_user_master",
        on_delete=deletion.PROTECT,
        null=True,
        blank=True,
    )

    @property
    def realm(self):
        return f"{self.transport.protocol}-{self.username}"

    @property
    def md5_cred(self):
        return md5(
            f"{self.username}:{self.secret}:{self.realm}".encode("utf-8")
        ).hexdigest()

    @property
    def standard_pjsip_user(self):
        return f"PJSIP/{self.username}"

    @property
    def standard_extension(self):
        return f"Dial({self.standard_pjsip_user}, 120, rtT);"

    @staticmethod
    def create_webrtc_account(username: str, user: User, context: DialplanContext):
        """
        Create WebRTC account for user
        :param username: username for account
        :param user: django user
        :return: SIPUser object
        """
        sip_user = SIPUser.objects.create(
            name=f"WebRTC account for {user.username}",
            username=username,
            secret=generate_32_char_password,
            transport=SIPTransport.objects.get(name="webrtc"),
            extension=username,
            context=context,
            master=user,  # Link to the Django user
        )
        return sip_user

    @transaction.atomic
    def save(
        self,
        force_insert: bool = False,
        force_update: bool = False,
        using: Optional[str] = None,
        update_fields: Optional[Iterable[str]] = None,
    ) -> None:
        if not self.pk:
            default_users_context = DialplanContext.getUsersOrCreateUsers()
            DialplanExtension.objects.create(
                context=default_users_context,
                ext=self.extension,
                dialplan=self.custom_extension or self.standard_extension,
                description=f"Extension for {self.username}",
            )
        else:
            previous_extension = self.__class__.objects.get(pk=self.pk).extension
            default_users_context = DialplanContext.getUsersOrCreateUsers()
            try:
                exten = DialplanExtension.objects.get(
                    context=default_users_context, ext=previous_extension
                )
                exten.ext = self.extension
                exten.dialplan = self.custom_extension or self.standard_extension
                exten.description = f"Extension for {self.username}"
                exten.save()
            except DialplanExtension.DoesNotExist:
                DialplanExtension.objects.create(
                    context=default_users_context,
                    ext=self.extension,
                    dialplan=self.custom_extension or self.standard_extension,
                    description=f"Extension for {self.username}",
                )

        return super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def __str__(self):
        return f"{self.username} ({self.name})"

    class Meta:
        verbose_name_plural = "02. SIP Users"


class SIPPeer(models.Model):
    description = models.CharField(
        default="",
        max_length=64,
        help_text="Describe a peer",
        verbose_name="Description",
    )
    name = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        default="",
        help_text="Name of the channel",
        verbose_name="Channel name",
    )
    username = models.CharField(
        max_length=32,
        unique=False,
        null=True,
        blank=True,
        help_text="Username for the connection used for remote side",
        verbose_name="Username",
    )
    secret = models.CharField(
        max_length=32,
        unique=False,
        null=False,
        blank=True,
        help_text="Clear text password for the connection used for remote side",
        verbose_name="Password",
    )
    host_port = models.CharField(
        max_length=256,
        null=True,
        blank=True,
        default="",
        help_text="Host:Port of the peer. Optional field. If not set registration will be allowed from anywhere.",
        verbose_name="The list of host[:port] separated by commas",
    )
    registrationHere = models.BooleanField(
        default=False,
        help_text="Should remote peer register here? Used for GSM, E1, T1, FXS, FXO gateways, etc. ",
        verbose_name="Registration here",
    )
    registrationThere = models.BooleanField(
        default=False,
        help_text="Should we register on remote service? Typically used for providers",
        verbose_name="Outbound registration",
    )
    nat = models.BooleanField(
        default=False,
        help_text="Enable NAT traversal for this peer",
        verbose_name="NAT",
    )
    callLimit = models.SmallIntegerField(
        default=0, help_text="Maximum calls on the trunk", verbose_name="Call Limit"
    )
    transport = models.ForeignKey(
        SIPTransport,
        related_name="sip_peer_transport",
        on_delete=deletion.PROTECT,
        null=True,
        blank=False,
    )
    routing_table = models.ForeignKey(
        RoutingTable,
        related_name="sip_peer_routing_table",
        on_delete=deletion.PROTECT,
        null=True,
        blank=True,
    )
    custom_auth_settings = models.TextField(
        null=True,
        blank=False,
        default="",
        help_text="Custom peer [auth] section",
        verbose_name="Auth Settings",
    )
    custom_aor_settings = models.TextField(
        null=True,
        blank=False,
        default="",
        help_text="Custom peer [aor] section",
        verbose_name="AOR Settings",
    )

    class Meta:
        verbose_name_plural = "03. SIP Uplinks and Peers"

    def __str__(self) -> str:
        return self.name


class DialplanMacro(models.Model):
    name = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        verbose_name="Macro name",
        help_text="Use latin symbols, digits and undercore",
    )
    description = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="Macro description",
        help_text="Use latin symbols, digits and undercore to describe",
    )
    macro = models.TextField(verbose_name="Macro scenario")

    class Meta:
        db_table = "dialplan_macros"
        verbose_name_plural = "06. Dialplan macros"


class DialplanExtension(models.Model):
    context = models.ForeignKey(
        DialplanContext,
        related_name="extensions",
        on_delete=deletion.PROTECT,
        null=True,
        blank=False,
    )
    ext = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=False,
        default="_X!",
        verbose_name="Extension",
        help_text="Asterisk extension",
        validators=[validate_asterisk_extension_prefix],
    )
    dialplan = models.TextField(
        verbose_name="Extension scenario",
        help_text="Use Asterisk AEL syntax to define the dialplan.",
    )
    description = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="Extension description",
        help_text="Use latin symbols, digits and undercore to describe",
    )

    @property
    def context_name(self):
        return self.context.name

    class Meta:
        db_table = "dialplan_extensions"
        verbose_name_plural = "05. Dialplan extensions"

        constraints = [
            models.UniqueConstraint(
                fields=["context", "ext"], name="unique extension inside context"
            )
        ]


class ManagerUsers(models.Model):
    username = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        verbose_name="Manager user name",
        help_text="Use latin symbols, digits and undercore",
    )
    secret = models.CharField(
        max_length=128,
        unique=True,
        null=False,
        blank=False,
        default=generate_64_char_password,
        verbose_name="Manager user secret",
        help_text="Password for manager user",
    )
    read = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=False,
        default="system,call,log,verbose,command,agent,user,config",
    )
    write = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=False,
        default="system,call,log,verbose,command,agent,user,config",
    )
    writetimeout = models.PositiveIntegerField(default=100, null=False, blank=False)
    eventfilter = models.CharField(
        max_length=64,
        unique=False,
        null=True,
        blank=True,
        default="!Event: RTCP*|!Event: VarSet|!Event: Cdr",
    )
    deny = models.CharField(max_length=64, unique=False, null=True, blank=True)
    permit = models.CharField(max_length=64, unique=False, null=True, blank=True)
    acl = models.CharField(max_length=64, unique=False, null=True, blank=True)

    class Meta:
        db_table = "manager_users"
        verbose_name_plural = "95. Manager users"


class Settings(models.Model):
    ip_addr_for_provisioning = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP address for provisioning",
        help_text="IP address for provisioning",
    )

    domain = models.CharField(
        max_length=64,
        unique=True,
        null=False,
        blank=False,
        default="127.0.0.1",
        verbose_name="Hostname of the server",
        help_text="Hostname of the server",
    )

    wss_port = models.SmallIntegerField(
        default=8089,
        null=False,
        blank=False,
        verbose_name="WSS port of the server",
        help_text="WSS port of the server",
    )
    allow_monitor = models.BooleanField(
        default=False,
        verbose_name="Allow global monitor",
        help_text="Allow to monitor calls of whole system",
    )

    @property
    def wss_url(self):
        return f"wss://{self.domain}:{self.wss_port}/ws"

    user_template = models.TextField(
        default="""type=endpoint
context=default
allow=!all, g722, ulaw, alaw
direct_media=no
trust_id_outbound=yes
device_state_busy_at=1
dtmf_mode=rfc4733
transport=transport-udp-nat
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
""",
        verbose_name="User basic template",
        help_text="You may override it by custom settings in user form",
    )

    user_aor_template = models.TextField(
        default="""type=aor
max_contacts=1
remove_existing=yes
""",
        verbose_name="User AOR template",
        help_text="You may override it by custom settings in user form",
    )

    user_auth_template = models.TextField(
        default="""type=auth
auth_type=md5
""",
        verbose_name="User auth template",
        help_text="You may override it by custom settings in user form",
    )

    webrtc_template = models.TextField(
        default="""
dtls_auto_generate_cert=yes
webrtc=yes
context=default
max_audio_streams=1
max_video_streams=15
disallow=all
allow=opus,g722,ulaw,vp9,vp8,h264
""",
        verbose_name="WebRTC template for endpoint",
        help_text="You may override it by custom settings in user form",
    )

    webrtc_aor_template = models.TextField(
        default="""type=aor
max_contacts=15
remove_existing=yes
""",
        verbose_name="WebRTC AOR template",
        help_text="You may override it by custom settings in user form",
    )

    webrtc_auth_template = models.TextField(
        default="""type=auth
auth_type=md5
""",
        verbose_name="WebRTC auth template",
        help_text="You may override it by custom settings in user form",
    )

    def save(self, *args, **kwargs):
        self.pk = self.id = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return "Settings single instance"

    class Meta:
        verbose_name_plural = "96. General Settings"


class MusicOnHoldModes(models.TextChoices):
    FILES = "files", "Files"
    PLAYLIST = "playlist", "Playlist"
    CUSTOM = "custom", "Custom"


class MusicOnHoldSortModes(models.TextChoices):
    RANDOM = "random", "Random"
    ALPHA = "alpha", "Alpha"


class MusicOnHold(models.Model):
    name = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        verbose_name="Music on hold name",
        help_text="Use latin symbols, digits and undercore",
    )

    mode = models.CharField(
        max_length=32,
        default=1,
        choices=MusicOnHoldModes.choices,
        null=True,
        blank=False,
    )

    directory = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="Directory",
        help_text="Directory with music files",
    )

    sort = models.CharField(
        max_length=32,
        default=1,
        choices=MusicOnHoldSortModes.choices,
        null=True,
        blank=False,
    )

    def _get_moh_base_path(self):
        """Returns the base path for MOH files based on DEVMODE setting."""
        if settings.DEVMODE == settings.DEVMODE_WITHOUT_ASTERISK:
            return "moh/"
        return "/var/lib/asterisk/moh/"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.directory:
            moh_path = os.path.join(self._get_moh_base_path(), self.directory)
            try:
                os.makedirs(moh_path, exist_ok=True)
            except PermissionError:
                pass  # Skip directory creation if no permissions (e.g., during tests)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "music_on_hold"
        verbose_name_plural = "08. Music on hold classes"


def moh_file_upload_path(instance, filename):
    """
    Побудова шляху для збереження файлу на основі каталогу классу MusicOnHold.
    """
    ext = filename.split(".")[-1]
    base_name = filename.rsplit(".", 1)[0]
    directory = instance.moh_class.directory if instance.moh_class else "default"
    return f"{directory}/{base_name}.{ext}"


class MusicOnHoldPlaylistEntry(models.Model):
    VALID_EXTENSIONS = ["mp3", "wav", "gsm", "ogg", "alaw", "al", "ulaw", "ul"]

    def validate_file_extension(value):
        ext = str(value).split(".")[-1]
        if ext.lower() not in MusicOnHoldPlaylistEntry.VALID_EXTENSIONS:
            raise ValidationError(
                "Unsupported file extension. Only mp3, wav, gsm, ogg, alaw, al, ulaw, and ul files are allowed."
            )

    def validate_file_size(value):
        max_size = 10 * 1024 * 1024  # 10 MB
        if value.size > max_size:
            raise ValidationError("File size exceeds 10 MB")

    file = models.FileField(
        storage=MOHFileSystemStorage(),
        upload_to=moh_file_upload_path,
        verbose_name="Playlist entry file",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=VALID_EXTENSIONS),
            validate_file_extension,
            validate_file_size,
        ],
    )

    url = models.URLField(verbose_name="Playlist entry url", blank=True, null=True)
    moh_class = models.ForeignKey(
        MusicOnHold, related_name="moh_class", on_delete=deletion.PROTECT, blank=True
    )

    def save(self, *args, **kwargs):
        if self.file:
            self.url = None
        elif self.url:
            self.file = None
        else:
            raise ValidationError("You must select either file or url")

        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.file:
            return f"{self.file}"
        elif self.url:
            return f"{self.url}"
        else:
            return "Unknown"

    class Meta:
        db_table = "moh_playlist_entry"
        verbose_name_plural = "07. Music on hold playlist entries"


class Queue(models.Model):
    STRATEGY_CHOICES = [
        ("ringall", "Ring All"),
        ("leastrecent", "Least Recent"),
        ("fewestcalls", "Fewest Calls"),
        ("random", "Random"),
        ("rrmemory", "Round Robin Memory"),
        ("rrordered", "Round Robin Ordered"),
        ("linear", "Linear as configured"),
        ("wrandom", "Weighted Random"),
    ]

    name = models.CharField(
        max_length=64, unique=True, null=False, blank=False, verbose_name="Queue Name"
    )
    music_class = models.ForeignKey(
        MusicOnHold,
        on_delete=models.PROTECT,
        related_name="queues",
        verbose_name="Music on hold",
    )
    announce = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name="Announcement to the member",
        help_text="""An announcement may be specified which is played for the member as
soon as they answer a call, typically to indicate to them which queue
this call should be answered as, so that agents or members who are
listening to more than one queue can differentiated how they should
engage the customer""",
    )
    queue_announce = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name="Queue announcement to the caller",
        help_text="""An announcement may be specified which is played to the caller just
before they are bridged with an agent.""",
    )
    strategy = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=STRATEGY_CHOICES,
        verbose_name="Strategy",
    )
    service_level = models.IntegerField(default=0, verbose_name="Service Level")
    context = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name="Context",
        help_text="""If a 'context' is specified, and a caller enters an extension that
matches an extension within that context, they will be taken out of
the queue and sent to that extension.""",
    )

    maxlen = models.PositiveIntegerField(default=0, verbose_name="Maximum Queue Length")
    timeout = models.PositiveIntegerField(default=15, verbose_name="Timeout")
    retry = models.PositiveIntegerField(default=5, verbose_name="Retry")
    timeoutpriority = models.CharField(
        max_length=4,
        default="app",
        choices=[("app", "Application"), ("conf", "Configuration")],
        verbose_name="Timeout Priority",
    )
    weight = models.PositiveIntegerField(default=0, verbose_name="Queue Weight")
    wrapuptime = models.PositiveIntegerField(default=0, verbose_name="Wrap-Up Time")
    autofill = models.BooleanField(default=True, verbose_name="Autofill")
    autopause = models.CharField(
        max_length=3,
        default="yes",
        choices=[("yes", "Yes"), ("no", "No"), ("all", "All")],
        verbose_name="Autopause",
    )
    autopausedelay = models.PositiveIntegerField(
        default=60, verbose_name="Autopause Delay"
    )
    reportholdtime = models.BooleanField(default=False, verbose_name="Report Hold Time")
    setinterfacevar = models.BooleanField(
        default=False, verbose_name="Set Interface Variable"
    )
    setqueueentryvar = models.BooleanField(
        default=False, verbose_name="Set Queue Entry Variable"
    )
    setqueuevar = models.BooleanField(default=False, verbose_name="Set Queue Variable")
    announce_frequency = models.PositiveIntegerField(
        default=0, verbose_name="Announce Frequency"
    )
    announce_holdtime = models.BooleanField(
        default=False, verbose_name="Announce Hold Time"
    )
    min_announce_frequency = models.PositiveIntegerField(
        default=0, verbose_name="Minimum Announce Frequency"
    )
    periodic_announce_frequency = models.PositiveIntegerField(
        default=0, verbose_name="Periodic Announce Frequency"
    )
    random_periodic_announce = models.BooleanField(
        default=False, verbose_name="Random Periodic Announce"
    )
    relative_periodic_announce = models.BooleanField(
        default=False, verbose_name="Relative Periodic Announce"
    )
    announce_holdtime = models.CharField(
        max_length=4,
        default="no",
        choices=[("yes", "Yes"), ("no", "No"), ("once", "Once")],
        verbose_name="Announce Hold Time",
        help_text="Should we include estimated hold time in position announcements?",
    )

    announce_position = models.CharField(
        max_length=5,
        default="no",
        choices=[("yes", "Yes"), ("no", "No"), ("more", "More"), ("limit", "Limit")],
        verbose_name="Announce Position",
    )

    announce_to_first_user = models.BooleanField(
        default=False, verbose_name="Announce to first user"
    )
    announce_position_limit = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100)],
        verbose_name="Announce Position Limit",
    )
    announce_round_seconds = models.PositiveIntegerField(
        default=0,
        choices=[
            (0, "0"),
            (5, "5"),
            (10, "10"),
            (15, "15"),
            (20, "20"),
            (25, "25"),
            (30, "30"),
        ],
        verbose_name="Announce Round Seconds",
    )
    announce_position_only_up = models.BooleanField(
        default=False,
        verbose_name="Announce position only up",
        help_text="Only announce the caller's position if it has improved since the last announcement.",
    )

    queue_announcement = models.ForeignKey(
        "QueueAnnouncements",
        on_delete=models.CASCADE,
        related_name="queues",
        verbose_name="Queue Announcement",
    )
    periodic_announce = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Periodic Announce",
        help_text="The list of files to announce separated by comma. Example: your-call-is-important-to-us, please-wait",
    )
    monitor_format = models.CharField(
        max_length=5,
        null=True,
        blank=True,
        choices=[("wav", "WAV"), ("gsm", "GSM"), ("wav49", "WAV49")],
        verbose_name="Monitor Format",
    )
    joinempty = models.CharField(
        max_length=100,
        default="paused,inuse,invalid",
        verbose_name="Join Empty",
        help_text="What to do when a caller joins a queue with no members in it?",
    )
    leavewhenempty = models.CharField(
        max_length=100,
        default="inuse,ringing",
        verbose_name="Leave When Empty",
        help_text="When to leave empty queue?",
    )
    ringinuse = models.BooleanField(default=False, verbose_name="Ring In Use")
    timeoutrestart = models.BooleanField(default=False, verbose_name="Timeout Restart")
    defaultrule = models.ForeignKey(
        "QueueRule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Default Rule",
        help_text="Escalation rule from queuerules.conf",
    )

    class Meta:
        db_table = "queues"
        verbose_name_plural = "09. Queues"

    def __str__(self):
        return self.name


class QueueMember(models.Model):
    queue = models.ForeignKey(
        Queue, on_delete=models.CASCADE, related_name="members", verbose_name="Queue"
    )
    interface = models.CharField(max_length=64, verbose_name="Interface")
    penalty = models.PositiveIntegerField(default=0, verbose_name="Penalty")
    member_name = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="Member Name"
    )
    state_interface = models.CharField(
        max_length=64, null=True, blank=True, verbose_name="State Interface"
    )
    ringinuse = models.BooleanField(default=False, verbose_name="Ring In Use")
    wrapuptime = models.PositiveIntegerField(default=0, verbose_name="Wrap-Up Time")

    class Meta:
        db_table = "queue_members"
        verbose_name_plural = "10. Queue Members"

    def __str__(self):
        return f"{self.member_name} ({self.interface})"

    def __ringinuse__(self):
        return "yes" if self.ringinuse else "no"

    def __state_interface__(self):
        return self.state_interface if self.state_interface else ""


class QueueAnnouncements(models.Model):
    name = models.CharField(
        max_length=64,
        unique=True,
        null=False,
        blank=False,
        verbose_name="Announcement name",
        default="default",
    )
    queue_youarenext = models.CharField(max_length=255, blank=True, null=True)
    queue_thereare = models.CharField(max_length=255, blank=True, null=True)
    queue_callswaiting = models.CharField(max_length=255, blank=True, null=True)
    queue_quantity1 = models.CharField(max_length=255, blank=True, null=True)
    queue_quantity2 = models.CharField(max_length=255, blank=True, null=True)
    queue_holdtime = models.CharField(max_length=255, blank=True, null=True)
    queue_minute = models.CharField(max_length=255, blank=True, null=True)
    queue_minutes = models.CharField(max_length=255, blank=True, null=True)
    queue_seconds = models.CharField(max_length=255, blank=True, null=True)
    queue_thankyou = models.CharField(max_length=255, blank=True, null=True)
    queue_reporthold = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name}"

    class Meta:
        db_table = "queue_announcements"
        verbose_name_plural = "11. Queue Announcements"


class QueueRule(models.Model):
    """
    Represents a logical name for an escalation rule.
    For example: 'support_daytime', 'critical_escalation'
    """

    name = models.CharField(
        max_length=64,
        unique=True,
        help_text="Unique rule name (used in Queue(...,,,rule_name))",
    )

    description = models.TextField(
        blank=True, help_text="Description or notes for the rule"
    )

    def __str__(self):
        return self.name

    class Meta:
        db_table = "queue_rules"
        verbose_name = "Queue Rule"
        verbose_name_plural = "13. Queue Rules"


class PenaltyChange(models.Model):
    """
    Change of escalation parameters linked to a QueueRule.
    """

    rule = models.ForeignKey(
        QueueRule,
        on_delete=models.CASCADE,
        related_name="penalty_changes",
        help_text="Related queue rule",
    )

    seconds = models.PositiveIntegerField(
        help_text="After how many seconds in the queue this change is applied"
    )

    max_penalty = models.CharField(
        max_length=10,
        blank=True,
        default="",
        validators=[validate_penalty_value],
        help_text="Empty=skip, absolute (10) or relative (+3, -2) for QUEUE_MAX_PENALTY",
    )

    min_penalty = models.CharField(
        max_length=10,
        blank=True,
        default="",
        validators=[validate_penalty_value],
        help_text="Empty=skip, absolute (0) or relative (+1, -1) for QUEUE_MIN_PENALTY",
    )

    raise_penalty = models.CharField(
        max_length=10,
        blank=True,
        default="",
        validators=[validate_penalty_value],
        help_text="Empty=skip, absolute (5) or relative (+1, -1) for QUEUE_RAISE_PENALTY",
    )

    order = models.PositiveIntegerField(
        default=0,
        validators=[MaxValueValidator(100), MinValueValidator(0)],
        help_text="Execution order if there are rules with the same time",
    )

    def __str__(self):
        return f"{self.rule.name} @ {self.seconds}s"

    class Meta:
        db_table = "penalty_changes"
        verbose_name = "Penalty Change"
        verbose_name_plural = "Penalty Changes"
        ordering = ["rule", "seconds", "order"]


class ConfigurationFile(models.Model):
    name = models.CharField(
        max_length=32,
        null=False,
        blank=False,
        verbose_name="File name",
        help_text="Use latin symbols, digits and undercore",
    )
    description = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="File description",
        help_text="Use latin symbols, digits and undercore to describe",
    )
    content = models.TextField(verbose_name="File content")
    path = models.CharField(
        max_length=256,
        unique=False,
        null=False,
        blank=False,
        verbose_name="File path",
        help_text="Use latin symbols, digits and undercore",
    )
    version = models.SmallIntegerField(
        default=1,
        null=False,
        blank=False,
        verbose_name="File version",
        help_text="File version",
    )
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.name} v.{self.version}"

    class Meta:
        db_table = "configuration_files"
        verbose_name_plural = "97. Configuration files"
        unique_together = ("name", "version")


class BinaryFile(models.Model):
    name = models.CharField(
        max_length=32,
        unique=True,
        null=False,
        blank=False,
        verbose_name="File name",
        help_text="Use latin symbols, digits and undercore",
    )
    description = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="File description",
        help_text="Use latin symbols, digits and undercore to describe",
    )
    content = models.BinaryField(verbose_name="File content")
    path = models.CharField(
        max_length=256,
        unique=False,
        null=False,
        blank=False,
        verbose_name="File path",
        help_text="Use latin symbols, digits and undercore",
    )
    version = models.SmallIntegerField(
        default=1,
        null=False,
        blank=False,
        verbose_name="File version",
        help_text="File version",
    )

    class Meta:
        db_table = "binary_files"
        verbose_name_plural = "98. Binary files"
        unique_together = ("name", "version")


class SystemConfiguration(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    description = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=True,
        verbose_name="Configuration description",
        help_text="Use latin symbols, digits and undercore to describe",
    )

    configuration_files = models.ManyToManyField(
        ConfigurationFile,
        verbose_name="Configuration Files",
        related_name="system_configurations",
        blank=True,
    )

    binary_files = models.ManyToManyField(
        BinaryFile,
        verbose_name="Binary Files",
        related_name="system_configurations",
        blank=True,
    )

    class Meta:
        db_table = "system_configurations"
        verbose_name_plural = "99. System Configurations"

    def __str__(self):
        return self.created.strftime("%Y-%m-%d %H:%M:%S")


class CallQueueGlobalSettings(models.Model):
    # Persistent Members
    persistent_members = models.BooleanField(
        default=True,
        verbose_name="Persistent Members",
        help_text="Store each dynamic member in each queue in the astdb so that when Asterisk is restarted, each member will be automatically read into their recorded queues.",
    )

    # AutoFill Behavior
    autofill = models.BooleanField(
        default=False,
        verbose_name="AutoFill Behavior",
        help_text="The old behavior of the queue (autofill=no) is to have a serial type behavior in that the queue will make all waiting callers wait in the queue even if there is more than one available member ready to take calls until the head caller is connected with the member they were trying to get to. The new behavior, enabled by setting autofill=yes makes sure that when the waiting callers are connecting with available members in a parallel fashion until there are no more available members or no more waiting callers. This is probably more along the lines of how a queue should work and in most cases, you will want to enable this behavior. If you do not specify or comment out this option, it will default to no.",
    )

    # Monitor Type
    monitor_type = models.CharField(
        max_length=50,
        default="MixMonitor",
        verbose_name="Monitor Type",
        help_text="By setting monitor-type = MixMonitor, when specifying monitor-format to enable recording of queue member conversations, app_queue will now use the new MixMonitor application instead of Monitor so the concept of 'joining/mixing' the in/out files now goes away when this is enabled. You can set the default type for all queues here, and then also change monitor-type for individual queues within a queue by using the same configuration parameter within a queue configuration block. If you do not specify or comment out this option, it will default to the old 'Monitor' behavior to keep backward compatibility.",
    )

    # Shared Lastcall
    shared_lastcall = models.BooleanField(
        default=False,
        verbose_name="Shared Lastcall",
        help_text="shared_lastcall will make the lastcall and calls received be the same in members logged in more than one queue. This is useful to make the queue respect the wrapuptime of another queue for a shared member. The default value is no.",
    )

    # Negative Penalty Invalid
    negative_penalty_invalid = models.BooleanField(
        default=False,
        verbose_name="Negative Penalty Invalid",
        help_text="negative_penalty_invalid = no",
    )

    # Log Membername as Agent
    log_membername_as_agent = models.BooleanField(
        default=False,
        verbose_name="Log Membername as Agent",
        help_text="log_membername_as_agent will cause app_queue to log the membername rather than the interface for the ADDMEMBER and REMOVEMEMBER events when a state_interface is set. The default value (no) maintains backward compatibility.",
    )

    # Force Longest Waiting Caller
    force_longest_waiting_caller = models.BooleanField(
        default=False,
        verbose_name="Force Longest Waiting Caller",
        help_text="force_longest_waiting_caller will cause app_queue to make sure callers are offered in order (longest waiting first), even for callers across multiple queues. Before a call is offered to an agent, an additional check is made to see if the agent is a member of another queue with a call that's been waiting longer. If so, the current call is not offered to the agent. The default value is 'no'.",
    )

    def save(self, *args, **kwargs):
        self.pk = self.id = 1
        return super().save(*args, **kwargs)

    def __str__(self):
        return "Call Queue Global Settings"

    class Meta:
        db_table = "call_queue_global_settings"
        verbose_name_plural = "12. Queue Global Settings"


class TrunkGroup(models.Model):
    name = models.CharField(
        max_length=64,
        unique=True,
        help_text="Name of the trunk group",
        verbose_name="Trunk Group Name",
    )
    sip_peers = models.ManyToManyField(
        SIPPeer,
        related_name="trunk_groups",
        blank=True,
        help_text="SIP Peers in the trunk group",
        verbose_name="SIP Peers",
    )

    class Meta:
        verbose_name_plural = "14. Trunk Groups"

    def __str__(self):
        return self.name


class RoutingRecord(models.Model):
    name = models.CharField(
        max_length=64,
        unique=False,
        help_text="Name of the routing record",
        verbose_name="Routing Record Name",
    )
    prefix = models.CharField(
        max_length=64,
        unique=False,
        help_text="Prefix of the routing record",
        verbose_name="Routing Record Prefix",
        validators=[validate_asterisk_extension_prefix],
    )
    context = models.ForeignKey(
        DialplanContext,
        related_name="routing_records",
        on_delete=deletion.PROTECT,
        blank=True,
        null=True,
        help_text="Context for the routing record",
        verbose_name="Routing Record Context",
    )
    routing_table = models.ForeignKey(
        RoutingTable,
        related_name="routing_records",
        on_delete=deletion.PROTECT,
        blank=True,
        null=True,
        help_text="Routing table for the routing record",
        verbose_name="Routing Table",
    )

    @staticmethod
    def getUsersOrCreateUsers():
        """
        Get or create users routing record
        :return: RoutingRecord object
        """
        try:
            users_routing_record = RoutingRecord.objects.get(
                name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD
            )
        except RoutingRecord.DoesNotExist:
            # Assuming that there's a method to get or create a proper default context
            users_context = DialplanContext.getUsersOrCreateUsers()
            users_routing_record = RoutingRecord.objects.create(
                name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD,
                prefix=settings.PEARLPBX_DEFAULT_ROUTING_PREFIX,
                context=users_context,
                routing_table=RoutingTable.getDefaultOrCreateDefault(),
            )
        return users_routing_record

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "16. Routing Records"


class Blacklist(AuditFields):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    callerid = models.CharField(
        max_length=64,
        unique=True,
        help_text="Caller ID to block",
        verbose_name="Caller ID",
    )
    destination = models.CharField(
        max_length=64,
        help_text="Destination number where calls must be blocked. Default="
        " for whole system blocking.",
        verbose_name="Destination",
        default="",
        blank=True,
        null=False,
    )
    reason = models.CharField(
        max_length=64,
        help_text="Reason for blocking the caller ID",
        verbose_name="Reason",
        default="",
    )
    expiration_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Expiration date for the blacklist entry. If not set, the entry is permanent.",
        verbose_name="Expiration Date",
    )

    class Meta:
        db_table = "blacklist"
        verbose_name_plural = "17. Blacklist"

    def __str__(self):
        return f"{self.callerid} - {self.reason}"


class Whitelist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    callerid = models.CharField(
        max_length=64,
        unique=True,
        help_text="Caller ID to allow",
        verbose_name="Caller ID",
    )
    destination = models.CharField(
        max_length=64,
        help_text="Destination number where calls must be allowed. Default="
        " for whole system allowing.",
        verbose_name="Destination",
        default="",
        blank=True,
        null=False,
    )
    reason = models.CharField(
        max_length=64,
        help_text="Reason for allowing the caller ID",
        verbose_name="Reason",
        default="",
    )
    expiration_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Expiration date for the whitelist entry. If not set, the entry is permanent.",
        verbose_name="Expiration Date",
    )

    class Meta:
        db_table = "whitelist"
        verbose_name_plural = "18. Whitelist"

    def __str__(self):
        return f"{self.callerid} - {self.reason}"


class Contact(AuditFields):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    callerid = models.CharField(
        max_length=64,
        unique=True,
        help_text="Caller ID to recognize",
        verbose_name="Caller ID",
    )
    name = models.CharField(
        max_length=64, help_text="Name of the caller ID", verbose_name="Name"
    )

    class Meta:
        db_table = "contacts"
        verbose_name_plural = "19. Contacts"

    def __str__(self):
        return f"{self.name} <{self.callerid}>"


def sound_file_upload_path(instance, filename):
    """
    Побудова шляху для збереження файлу на основі мови.
    """
    ext = filename.split(".")[-1]
    base_name = instance.name or filename.rsplit(".", 1)[0]
    return f"{instance.language}/{base_name}.{ext}"


class SoundFile(models.Model):
    VALID_EXTENSIONS = ["mp3", "wav", "gsm", "ogg", "alaw", "al", "ulaw", "ul"]

    def validate_file_extension(value):
        ext = str(value).split(".")[-1]
        if ext.lower() not in SoundFile.VALID_EXTENSIONS:
            raise ValidationError(
                "Unsupported file extension. Only mp3, wav, gsm, ogg, alaw, al, ulaw, and ul files are allowed."
            )

    def validate_file_size(value):
        max_size = 10 * 1024 * 1024  # 10 MB
        if value.size > max_size:
            raise ValidationError("File size exceeds 10 MB")

    file = models.FileField(
        storage=SoundsFileSystemStorage(),
        upload_to=sound_file_upload_path,
        verbose_name="Sound file",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=VALID_EXTENSIONS),
            validate_file_extension,
            validate_file_size,
        ],
    )

    name = models.CharField(
        max_length=64,
        null=False,
        blank=False,
        verbose_name="File name used in dialplans",
        help_text="The file name without extension. You may enter completely different name here.",
    )

    language = models.CharField(
        max_length=3,
        unique=False,
        null=False,
        blank=True,
        verbose_name="Language",
        help_text="Language of the sound file",
    )

    def __str__(self) -> str:
        return f"{self.language} - {self.name} - {self.file}"

    class Meta:
        db_table = "sound_files"
        verbose_name_plural = "20. Sound files"
        unique_together = [["name", "language"]]


class Monitor(models.Model):
    callerid = models.CharField(
        max_length=64,
        blank=True,
        null=False,
        help_text="Caller ID to monitor. Blank for all calls.",
        verbose_name="Caller ID",
    )
    destination = models.CharField(
        max_length=64,
        blank=True,
        null=False,
        help_text="Destination to monitor. Blank for all destinations.",
        verbose_name="Destination",
    )
    force_enable_monitor = models.BooleanField(
        default=False,
        help_text="Force enable monitor for this caller ID and destination",
        verbose_name="Force Enable Monitor",
    )
    force_disable_monitor = models.BooleanField(
        default=False,
        help_text="Force disable monitor for this caller ID and destination",
        verbose_name="Force Disable Monitor",
    )
    created = models.DateTimeField(auto_now_add=True, verbose_name="Created")
    modified = models.DateTimeField(auto_now=True, verbose_name="Modified")

    class Meta:
        constraints = [
            # Один із callerid або destination має бути заповнений
            models.CheckConstraint(
                condition=~Q(callerid="") | ~Q(destination=""),  # type: ignore
                name="callerid_or_destination_required",
            ),
            # force_enable_monitor і force_disable_monitor не можуть бути однаковими
            models.CheckConstraint(
                condition=~Q(force_enable_monitor=F("force_disable_monitor")),  # type: ignore
                name="force_enable_not_equal_disable",
            ),
        ]

    def __str__(self):
        return (
            f'Monitor("{self.callerid}" -> "{self.destination}" = '
            f"<{self.force_enable_monitor}, {self.force_disable_monitor}>)"
        )


class MonitorFilenames(models.Model):
    """Represent a mapping monitor filenames to CDR UniqueID."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    src = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=False,
        help_text="The caller ID associated with the monitor recording",
    )
    dst = models.CharField(
        max_length=64,
        unique=False,
        null=False,
        blank=False,
        help_text="The destination number associated with the monitor recording",
    )
    filename = models.CharField(
        max_length=255,
        unique=True,
        help_text="The filename of the monitor recording",
        verbose_name="Monitor Filename",
    )
    cdr_uniqueid = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text="The unique ID of the CDR associated with this monitor recording",
        verbose_name="CDR UniqueID",
    )
    created = models.DateTimeField(auto_now_add=True, verbose_name="Created")
    requested_by_api = models.BooleanField(
        default=False,
        help_text="Indicates if the filename is requested by API usage",
        verbose_name="Requested by API",
    )
    used_by_system = models.BooleanField(
        default=False,
        help_text="Indicates if the filename is used by the system",
        verbose_name="Used by System",
    )
    # Automatically update the modified timestamp on save
    modified = models.DateTimeField(auto_now=True, verbose_name="Modified")

    class Meta:
        db_table = "core_monitor_filenames"
        indexes = [
            models.Index(fields=["src", "dst"], name="idx_src_dst"),
            models.Index(fields=["cdr_uniqueid"], name="idx_cdr_uniqueid"),
            models.Index(fields=["created"], name="idx_created"),
            models.Index(fields=["filename"], name="idx_filename"),
        ]

    def monitor_filename(self) -> str:
        return self.filename

    def get_audio_file_path(self, ext: Optional[str] = None) -> str:
        """Return the full path to the audio file, optionally for a given extension."""
        if ext is None:
            # Default to .mp3, fallback to .wav if .mp3 does not exist
            mp3_path = os.path.join(
                settings.ASTERISK_MONITOR_DIR, self.monitor_filename() + ".mp3"
            )
            wav_path = os.path.join(
                settings.ASTERISK_MONITOR_DIR, self.monitor_filename() + ".wav"
            )
            if os.path.exists(mp3_path):
                return mp3_path
            return wav_path
        return os.path.join(
            settings.ASTERISK_MONITOR_DIR, self.monitor_filename() + ext
        )

    def audio_file_exists(self) -> bool:
        """Check if the audio file exists (either .mp3 or .wav)."""
        return os.path.exists(self.get_audio_file_path(ext=".mp3")) or os.path.exists(
            self.get_audio_file_path(ext=".wav")
        )

    def get_audio_url(self) -> str | None:
        """Return the URL for accessing the audio file, or None if not found."""
        if self.audio_file_exists():
            return reverse("audio_file", kwargs={"record_id": self.id})
        return None

    def __str__(self) -> str:
        return self.monitor_filename()
