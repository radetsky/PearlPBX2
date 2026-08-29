import os
import secrets
import shutil
import string

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    DialplanContext,
    DialplanExtension,
    DialplanGlobalVariable,
    MusicOnHold,
    MusicOnHoldModes,
    MusicOnHoldSortModes,
    Queue,
    QueueAnnouncements,
    QueueMember,
    RoutingRecord,
    RoutingTable,
    SIPPeer,
    SIPTransport,
    SIPUser,
    SoundFile,
)

CONTRIB_DIR = os.path.join(str(settings.BASE_DIR), "contrib")

# (dialplan body, description) for each extension, keyed by extension pattern.
# Bodies are the AEL block content only — core.conf.make_dialplan_extension
# wraps them in "{ext} => { ... }".
IVR_MAIN_EXTENSIONS = {
    "_X.": (
        "Answer();\n"
        "Wait(1);\n"
        "Set(IVR_RETRY=0);\n"
        "goto s,1;",
        "Entry point for any inbound call routed here",
    ),
    "s": (
        "Set(TIMEOUT(digit)=3);\n"
        "Set(TIMEOUT(response)=7);\n"
        "Set(IVR_RETRY=$[${IVR_RETRY} + 1]);\n"
        "Background(welcome-quickstart);\n"
        "WaitExten(7);",
        "Play the menu and wait for 1 (Sales) or 2 (Support)",
    ),
    "1": ("goto quickstart-services,141,1;", "Sales"),
    "2": ("goto quickstart-services,142,1;", "Support"),
    "i": (
        "Playback(invalid);\n"
        "if (${IVR_RETRY} < 3) {\n"
        "    goto s,1;\n"
        "}\n"
        "goto quickstart-services,141,1;",
        "Invalid digit — retry twice, then fall back to Sales",
    ),
    "t": (
        "if (${IVR_RETRY} < 3) {\n"
        "    goto s,1;\n"
        "}\n"
        "goto quickstart-services,141,1;",
        "No input — retry twice, then fall back to Sales",
    ),
}

QUICKSTART_SERVICES_EXTENSIONS = {
    "140": (
        "Answer();\nWait(1);\ngoto ivr-main,s,1;",
        "Test the IVR from an internal phone",
    ),
    "141": (
        "Answer();\nQueue(Sales,tT,,,300);\nPlayback(vm-goodbye);\nHangup();",
        "Sales queue",
    ),
    "142": (
        "Answer();\nQueue(Support,tT,,,300);\nPlayback(vm-goodbye);\nHangup();",
        "Support queue",
    ),
}

OUTBOUND_EXTERNAL_EXTENSIONS = {
    "_X.": (
        "NoOp(CALL BEGIN >>>> :'${CALLERID(name)}'@<${CALLERID(num)}>);\n"
        "Set(CHANNEL(language)=ua);\n"
        "Set(TIMEOUT(absolute)=3600);\n"
        "// Set(CALLERID(num)=?\n"
        "// Turn on record of the call except rules in the database\n"
        "AGI(agi://127.0.0.1:4573/mixmonitor,${CALLERID(num)},${EXTEN});\n"
        "NoOp(Outbound call to ${EXTEN} via myprovider);\n"
        "Dial(PJSIP/${EXTEN}@myprovider,120,tT);\n"
        "Hangup();",
        "Outbound calls via the example trunk",
    ),
}


class Command(BaseCommand):
    help = (
        "Seed demo Sales/Support queues, an example inbound IVR (1=Sales, 2=Support), "
        "an example SIP trunk, Incoming/Outgoing routing tables, and 10 'webrtcuser*' "
        "WebRTC (wss) SIP users each with a random password. Intended to run exactly once, "
        "on a fresh install — see --force to re-run on a populated DB."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even if quick-start data already appears to be present.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be done without writing to the database.",
        )
        parser.add_argument(
            "--show-credentials",
            action="store_true",
            help="Print the example trunk credentials and seeded numbering plan after seeding.",
        )

    def handle(self, *args, **options):
        if self._already_seeded() and not options["force"]:
            self.stdout.write(
                "Quick-start data already present (found a Queue, a SIPPeer, or an "
                "Incoming/Outgoing routing table) — nothing to do. Use --force to seed anyway."
            )
            return

        if options["dry_run"]:
            self.stdout.write(
                "Dry run: would seed MOH, queue announcements, Sales/Support queues, "
                "the welcome-quickstart sound file, the example 'myprovider' trunk, "
                "the ivr-main/quickstart-services/outbound-external dialplan contexts, "
                "the Incoming/Outgoing routing tables, TRANSFER_CONTEXT, a WebRTC (wss) "
                "transport and 10 'webrtcuser*' SIP users each with a random password, "
                "and move all SIP users onto the Outgoing routing table."
            )
            return

        with transaction.atomic():
            moh = self._seed_moh()
            announcements = self._seed_queue_announcements()
            self._seed_queues(moh, announcements)
            self._seed_sound_file()
            transport = self._get_default_transport()
            incoming = self._get_or_create_routing_table("Incoming")
            outgoing = self._get_or_create_routing_table("Outgoing")
            self._seed_trunk(transport, incoming)
            self._seed_webrtc_users(outgoing)
            self._seed_dialplan()
            self._seed_routing_records(incoming, outgoing)
            self._seed_globals()
            moved = self._move_users_to_outgoing(outgoing)

        self.stdout.write(
            self.style.SUCCESS(
                f"Quick-start data seeded. Moved {moved} SIP user(s) onto the Outgoing routing table."
            )
        )

        if options["show_credentials"]:
            self._print_credentials()

    def _already_seeded(self):
        return (
            Queue.objects.exists()
            or SIPPeer.objects.exists()
            or RoutingTable.objects.filter(name__in=("Incoming", "Outgoing")).exists()
        )

    def _seed_moh(self):
        moh, created = MusicOnHold.objects.get_or_create(
            name="default",
            defaults={
                "mode": MusicOnHoldModes.FILES,
                "directory": "default",
                "sort": MusicOnHoldSortModes.RANDOM,
            },
        )
        if created:
            self.stdout.write("Created MusicOnHold class 'default'")

        src = os.path.join(CONTRIB_DIR, "moh", "on_hold_music.wav")
        if not os.path.exists(src):
            self.stdout.write(
                self.style.WARNING(
                    f"{src} not found — the default MOH class will have no audio"
                )
            )
            return moh

        dest_dir = os.path.join(moh._get_moh_base_path(), moh.directory)
        dest = os.path.join(dest_dir, "on_hold_music.wav")
        if not os.path.exists(dest):
            try:
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copyfile(src, dest)
                self.stdout.write(f"Copied on_hold_music.wav into {dest_dir}")
            except OSError as exc:
                self.stdout.write(self.style.WARNING(f"Could not copy MOH file: {exc}"))
        return moh

    def _seed_queue_announcements(self):
        announcements, created = QueueAnnouncements.objects.get_or_create(
            name="default",
            defaults={
                "queue_youarenext": "queue-youarenext",
                "queue_thereare": "queue-thereare",
                "queue_callswaiting": "queue-callswaiting",
                "queue_holdtime": "queue-holdtime",
                "queue_minute": "queue-minute",
                "queue_minutes": "queue-minutes",
                "queue_seconds": "queue-seconds",
                "queue_thankyou": "queue-thankyou",
                "queue_reporthold": "queue-reporthold",
            },
        )
        if created:
            self.stdout.write("Created default QueueAnnouncements")
        return announcements

    def _seed_queues(self, moh, announcements):
        users = list(SIPUser.objects.order_by("extension"))
        for name in ("Sales", "Support"):
            queue, created = Queue.objects.get_or_create(
                name=name,
                defaults={
                    "music_class": moh,
                    "queue_announcement": announcements,
                    "strategy": "rrmemory",
                    "timeout": 15,
                    "retry": 5,
                },
            )
            if created:
                self.stdout.write(f"Created queue '{name}'")

            for user in users:
                QueueMember.objects.get_or_create(
                    queue=queue,
                    interface=f"PJSIP/{user.username}",
                    defaults={
                        "member_name": user.name or user.username,
                        "penalty": 0,
                    },
                )

    def _seed_sound_file(self):
        src = os.path.join(CONTRIB_DIR, "sounds", "welcome-quickstart.ul")
        if not os.path.exists(src):
            self.stdout.write(
                self.style.WARNING(
                    f"{src} not found — the IVR references a missing "
                    "'welcome-quickstart' sound file"
                )
            )
            return

        if SoundFile.objects.filter(name="welcome-quickstart", language="en").exists():
            return

        with open(src, "rb") as f:
            sound = SoundFile(name="welcome-quickstart", language="en")
            sound.file.save("welcome-quickstart.ul", File(f), save=True)
        self.stdout.write("Registered the welcome-quickstart sound file")

    def _get_default_transport(self):
        transport = SIPTransport.objects.filter(protocol="udp").order_by("id").first()
        if transport:
            return transport
        transport, _ = SIPTransport.objects.get_or_create(
            name="transport-udp",
            defaults={
                "description": "Classic UDP transport",
                "protocol": "udp",
                "bind": "0.0.0.0:5060",
            },
        )
        return transport

    def _get_or_create_routing_table(self, name):
        routing_table, created = RoutingTable.objects.get_or_create(name=name)
        if created:
            self.stdout.write(f"Created routing table '{name}'")
        return routing_table

    def _seed_trunk(self, transport, incoming):
        peer, created = SIPPeer.objects.get_or_create(
            name="myprovider",
            defaults={
                "description": "Example SIP provider — replace before going live",
                "username": "test",
                "secret": "secret",
                "auth_type": "userpass",
                "registration_uri": "csbc.myprovider.net",
                "contact_uri": "csbc.myprovider.net",
                "match_hosts": "csbc.myprovider.net",
                "registrationHere": False,
                "registrationThere": True,
                "nat": True,
                "transport": transport,
                "routing_table": incoming,
            },
        )
        if created:
            self.stdout.write("Created example SIP trunk 'myprovider'")
        return peer

    def _get_or_create_wss_transport(self):
        transport, created = SIPTransport.objects.get_or_create(
            name="transport-wss",
            defaults={
                "description": "WebRTC (wss) transport",
                "protocol": "wss",
                "bind": "0.0.0.0",
            },
        )
        if created:
            self.stdout.write("Created WebRTC transport 'transport-wss'")
        return transport

    def _next_free_extension(self, start):
        taken = set(SIPUser.objects.values_list("extension", flat=True))
        ext = start
        while str(ext) in taken:
            ext += 1
        return str(ext)

    def _seed_webrtc_users(self, outgoing, count=10):
        transport = self._get_or_create_wss_transport()

        # The andrius/asterisk:22 Docker image has no codec_opus.so
        # translator (only the runtime lib and the SDP attribute module), so
        # negotiating opus there fails every Playback() with "Unable to find
        # a codec translation path". g722/ulaw both have working translators
        # in that image. A bare-metal/Ansible install is expected to have
        # Opus compiled in, so its seeded users keep Settings.webrtc_template
        # 's default allow list (opus first) untouched.
        custom_settings = (
            "disallow=all\nallow=g722,ulaw,vp9,vp8,h264\n"
            if settings.PEARLPBX2_DOCKER
            else ""
        )

        for i in range(1, count + 1):
            username = "webrtcuser" if i == 1 else f"webrtcuser{i}"
            if SIPUser.objects.filter(username=username).exists():
                continue

            secret = "".join(
                secrets.choice(string.ascii_letters + string.digits) for _ in range(16)
            )
            SIPUser.objects.create(
                name=f"WebRTC Test User {i}",
                username=username,
                secret=secret,
                transport=transport,
                extension=self._next_free_extension(211),
                routing_table=outgoing,
                auth_type="md5",
                custom_settings=custom_settings,
            )
            self.stdout.write(
                self.style.WARNING(
                    f"Created WebRTC test user '{username}' with password '{secret}' "
                    "(run 'manage.py export_sip_test_accounts' to retrieve it again later)"
                )
            )

    def _seed_context(self, name, description, extensions):
        context, created = DialplanContext.objects.get_or_create(
            name=name, defaults={"description": description}
        )
        if created:
            self.stdout.write(f"Created dialplan context '{name}'")
        for ext, (dialplan, ext_description) in extensions.items():
            DialplanExtension.objects.get_or_create(
                context=context,
                ext=ext,
                defaults={"dialplan": dialplan, "description": ext_description},
            )
        return context

    def _seed_dialplan(self):
        self._seed_context(
            "ivr-main",
            "Quick-start IVR: 1=Sales, 2=Support",
            IVR_MAIN_EXTENSIONS,
        )
        self._seed_context(
            "quickstart-services",
            "Quick-start Sales/Support queue entry points",
            QUICKSTART_SERVICES_EXTENSIONS,
        )
        self._seed_context(
            "outbound-external",
            "Quick-start outbound calls via the example trunk",
            OUTBOUND_EXTERNAL_EXTENSIONS,
        )

    def _seed_routing_records(self, incoming, outgoing):
        ivr_main = DialplanContext.objects.get(name="ivr-main")
        RoutingRecord.objects.get_or_create(
            routing_table=incoming,
            prefix="_X.",
            defaults={"name": "Quick-start IVR", "context": ivr_main},
        )

        services = DialplanContext.objects.get(name="quickstart-services")
        outbound_external = DialplanContext.objects.get(name="outbound-external")
        local_services = DialplanContext.objects.filter(name="local-services").first()
        # The per-user context SIPUser.save() maintains automatically (one
        # "Dial(PJSIP/<actual username>, ...)" extension per user) — not
        # "pearlpbx-local-users", which hardcodes a "ppbxuser${EXTEN}" Dial
        # target and only ever worked for users literally named that way.
        local_users = DialplanContext.getUsersOrCreateUsers()
        international = DialplanContext.objects.filter(name="international-calls").first()

        records = [
            ("Quick-start Sales/Support", "_14X", services),
            ("PearlPBX Local Users", "_2XX", local_users),
        ]
        if local_services:
            records.append(("Local Services", "_13X", local_services))
        if international:
            records.append(("Disable international calls", "_00X!", international))
        records.append(("Outbound external calls", "_X.", outbound_external))

        for name, prefix, context in records:
            RoutingRecord.objects.get_or_create(
                routing_table=outgoing,
                prefix=prefix,
                defaults={"name": name, "context": context},
            )

    def _seed_globals(self):
        DialplanGlobalVariable.objects.get_or_create(
            name="TRANSFER_CONTEXT",
            defaults={
                "value": "Outgoing",
                "description": "Routing table blind/attended transfers resolve into",
            },
        )

    def _move_users_to_outgoing(self, outgoing):
        return SIPUser.objects.exclude(routing_table=outgoing).update(
            routing_table=outgoing
        )

    def _print_credentials(self):
        self.stdout.write("")
        self.stdout.write("Example trunk 'myprovider' (replace before going live):")
        self.stdout.write("  registration_uri = csbc.myprovider.net")
        self.stdout.write("  username         = test")
        self.stdout.write("  secret           = secret")
        self.stdout.write("")
        self.stdout.write(
            "Seeded numbering plan: 130-132 (echo/queue login/logout), "
            "140 (IVR test), 141 (Sales), 142 (Support), 201-210 (users), "
            "'webrtcuser'/'webrtcuser2'..'webrtcuser10' (extensions 211-220) on "
            "transport-wss (see the WebRTC test user log lines above for their passwords)"
        )
        self.stdout.write(
            "Run 'manage.py export_sip_test_accounts' to get the 201-210 SIP passwords."
        )
