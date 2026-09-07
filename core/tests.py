from django.conf import settings
from django.test import TestCase
from core.models import (
    SIPTransport,
    SIPUser,
    SIPPeer,
    RoutingTable,
    RoutingRecord,
    DialplanContext,
    DialplanExtension,
    DialplanMacro,
    DialplanGlobalVariable,
    Settings,
    ManagerUsers,
    CallQueueGlobalSettings,
    Queue,
    QueueAnnouncements,
    QueueMember,
    QueueRule,
    PenaltyChange,
    MusicOnHold,
    MusicOnHoldPlaylistEntry,
    TrunkGroup,
)
from core.validators import validate_dialplan_field
from core.conf import (
    make_pjsip_conf_transports,
    make_pjsip_conf_uplinks,
    make_pjsip_conf_users,
    make_pjsip_conf_users_template,
    make_pjsip_conf_users_aor_template,
    make_pjsip_conf_users_auth_template,
    make_pjsip_webrtc_templates,
    make_pjsip_conf,
    make_extensions_ael,
    make_dialplan_contexts,
    make_dialplan_macros,
    make_dialplan_globals,
    make_dialplan_extension,
    make_routing_tables,
    make_manager_conf,
    make_queues_conf,
    make_queuerules_conf,
    make_musiconhold_conf,
    _asterisk_pattern_specificity,
)


class TestSIPTransport(TestCase):
    def setUp(self) -> None:
        SIPTransport.objects.create(
            bind="0.0.0.0",
            protocol="udp",
            name="udp-transport",
            description="UDP transport",
        )
        SIPTransport.objects.create(
            bind="0.0.0.0",
            protocol="tcp",
            name="tcp-transport",
            description="TCP transport",
        )
        SIPTransport.objects.create(
            bind="0.0.0.0",
            protocol="tls",
            name="tls-transport",
            description="TLS transport",
        )
        SIPTransport.objects.create(
            protocol="wss",
            name="wss-transport",
            description="WebSocket secure transport",
        )

    def test_sip_transports_exist(self):
        udp_transport = SIPTransport.objects.get(name="udp-transport")
        self.assertEqual(udp_transport.protocol, "udp")
        tcp_transport = SIPTransport.objects.get(name="tcp-transport")
        self.assertEqual(tcp_transport.protocol, "tcp")
        tls_transport = SIPTransport.objects.get(name="tls-transport")
        self.assertEqual(tls_transport.protocol, "tls")
        wss_transport = SIPTransport.objects.get(name="wss-transport")
        self.assertEqual(wss_transport.protocol, "wss")


class TestDefaultRoutingTable(TestCase):
    def test_default_routing_table_exists(self):
        name = settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        default_routing_table = RoutingTable.objects.get(name=name)
        self.assertEqual(default_routing_table.name, name)


class TestMakePjsipConfTransports(TestCase):
    def test_transports_section_header(self):
        result = make_pjsip_conf_transports()
        self.assertIn("; ==== Transports section ====", result)

    def test_basic_udp_transport(self):
        transport = SIPTransport.objects.create(
            name="test-transport-udp",
            protocol="udp",
            bind="0.0.0.0:5060",
            description="UDP Transport",
        )
        try:
            result = make_pjsip_conf_transports()
            self.assertIn("[test-transport-udp]", result)
            self.assertIn("type = transport", result)
            self.assertIn("protocol = udp", result)
            self.assertIn("bind = 0.0.0.0:5060", result)
            self.assertIn("; UDP Transport", result)
        finally:
            transport.delete()

    def test_transport_with_nat_settings(self):
        transport = SIPTransport.objects.create(
            name="test-transport-nat",
            protocol="udp",
            bind="0.0.0.0:5060",
            description="NAT Transport",
            external_media_address="203.0.113.1",
            external_signaling_address="203.0.113.1",
            local_nets="192.168.1.0/24, 10.0.0.0/8",
        )
        try:
            result = make_pjsip_conf_transports()
            self.assertIn("external_media_address = 203.0.113.1", result)
            self.assertIn("external_signaling_address = 203.0.113.1", result)
            self.assertIn("local_net = 192.168.1.0/24", result)
            self.assertIn("local_net = 10.0.0.0/8", result)
        finally:
            transport.delete()

    def test_multiple_transports(self):
        t1 = SIPTransport.objects.create(
            name="test-udp-transport",
            protocol="udp",
            bind="0.0.0.0:5060",
            description="UDP",
        )
        t2 = SIPTransport.objects.create(
            name="test-tcp-transport",
            protocol="tcp",
            bind="0.0.0.0:5060",
            description="TCP",
        )
        try:
            result = make_pjsip_conf_transports()
            self.assertIn("[test-udp-transport]", result)
            self.assertIn("[test-tcp-transport]", result)
            self.assertIn("protocol = udp", result)
            self.assertIn("protocol = tcp", result)
        finally:
            t1.delete()
            t2.delete()


class TestMakePjsipConfUplinks(TestCase):
    def setUp(self):
        self.transport = SIPTransport.objects.create(
            name="test-uplink-transport",
            protocol="udp",
            bind="0.0.0.0:5060",
            description="UDP Transport",
        )
        self.routing_table = RoutingTable.objects.get(
            name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )
        self.created_peers = []

    def tearDown(self):
        for peer in self.created_peers:
            peer.delete()
        self.transport.delete()

    def test_uplinks_section_header(self):
        result = make_pjsip_conf_uplinks()
        self.assertIn("; ==== Uplinks section ====", result)

    def test_basic_trunk_no_registration(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk1",
            transport=self.transport,
            routing_table=self.routing_table,
            contact_uri="sip.provider.com:5060",
            match_hosts="sip.provider.com",
            username="user1",
            secret="secret1",
            registrationHere=False,
            registrationThere=False,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("; test-trunk1", result)
        self.assertIn("[test-trunk1]", result)
        self.assertIn("type=endpoint", result)
        self.assertIn("type=aor", result)
        self.assertIn("type=identify", result)
        self.assertIn("; do not register on the remote side", result)

    def test_trunk_with_remote_registration(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-reg",
            transport=self.transport,
            routing_table=self.routing_table,
            registration_uri="sip.provider.com:5060",
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=False,
            registrationThere=True,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("type=registration", result)
        self.assertIn("server_uri=sip:sip.provider.com:5060;transport=udp", result)
        self.assertIn(
            "client_uri=sip:myuser@sip.provider.com:5060;transport=udp", result
        )
        self.assertIn("contact_user=myuser", result)
        self.assertIn("outbound_auth=test-trunk-reg", result)

    def test_trunk_with_outbound_registration_has_static_aor_contact(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-reg-contact",
            transport=self.transport,
            routing_table=self.routing_table,
            registration_uri="sip.provider.com:5060",
            contact_uri="sbc.provider.com:5061",
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=False,
            registrationThere=True,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("contact=sip:sbc.provider.com:5061", result)
        self.assertIn("max_contacts=1", result)
        self.assertIn("remove_existing=yes", result)

    def test_trunk_with_outbound_registration_falls_back_to_registration_uri(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-reg-fallback",
            transport=self.transport,
            routing_table=self.routing_table,
            registration_uri="sip.provider.com:5060",
            contact_uri="",
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=False,
            registrationThere=True,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("contact=sip:sip.provider.com:5060", result)

    def test_trunk_with_inbound_registration_has_no_static_aor_contact(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-reg-here",
            transport=self.transport,
            routing_table=self.routing_table,
            contact_uri="sbc.provider.com:5061",
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=True,
            registrationThere=False,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertNotIn("contact=sip:sbc.provider.com:5061", result)
        self.assertIn("max_contacts=1", result)
        self.assertIn("remove_existing=yes", result)

    def test_trunk_with_outbound_registration_tls_uses_sips_contact(self):
        tls_transport = SIPTransport.objects.create(
            name="test-uplink-tls-transport",
            protocol="tls",
            bind="0.0.0.0:5061",
            description="TLS Transport",
        )
        try:
            trunk = SIPPeer.objects.create(
                name="test-trunk-reg-tls",
                transport=tls_transport,
                routing_table=self.routing_table,
                registration_uri="sip.provider.com:5061",
                contact_uri="sbc.provider.com:5061",
                match_hosts="sip.provider.com",
                username="myuser",
                secret="mysecret",
                registrationHere=False,
                registrationThere=True,
            )
            result = make_pjsip_conf_uplinks()
            self.assertIn("contact=sips:sbc.provider.com:5061", result)
        finally:
            trunk.delete()
            tls_transport.delete()

    def test_trunk_with_both_registration_flags_keeps_bootstrap_contact(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-reg-both",
            transport=self.transport,
            routing_table=self.routing_table,
            registration_uri="sip.provider.com:5060",
            contact_uri="sbc.provider.com:5061",
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=True,
            registrationThere=True,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("contact=sip:sbc.provider.com:5061", result)
        self.assertIn("max_contacts=1", result)
        self.assertIn("remove_existing=yes", result)

    def test_trunk_without_registration_and_without_contact_logs_warning(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-no-contact",
            transport=self.transport,
            routing_table=self.routing_table,
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=False,
            registrationThere=False,
        )
        self.created_peers.append(trunk)
        with self.assertLogs("core.conf", level="WARNING") as logs:
            result = make_pjsip_conf_uplinks()
        self.assertIn("[test-trunk-no-contact]", result)
        self.assertNotIn("contact=sip:", result)
        self.assertTrue(
            any("no contact_uri or registration_uri defined" in m for m in logs.output)
        )

    def test_trunk_falls_back_to_registration_uri_logs_warning(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-reg-fallback-warn",
            transport=self.transport,
            routing_table=self.routing_table,
            registration_uri="sip.provider.com:5060",
            contact_uri="",
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=False,
            registrationThere=True,
        )
        self.created_peers.append(trunk)
        with self.assertLogs("core.conf", level="WARNING") as logs:
            result = make_pjsip_conf_uplinks()
        self.assertIn("contact=sip:sip.provider.com:5060", result)
        self.assertTrue(
            any("Falling back to registration_uri" in m for m in logs.output)
        )

    def test_trunk_with_nat_enabled(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-nat",
            transport=self.transport,
            routing_table=self.routing_table,
            match_hosts="sip.provider.com",
            username="user",
            secret="pass",
            nat=True,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("media_use_received_transport=yes", result)
        self.assertIn("rtp_symmetric=yes", result)
        self.assertIn("rewrite_contact=yes", result)
        self.assertIn("force_rport=yes", result)

    def test_trunk_with_custom_aor_settings(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-custom",
            transport=self.transport,
            routing_table=self.routing_table,
            custom_aor_settings="max_contacts=5\nqualify_frequency=60",
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("; Custom AOR settings for test-trunk-custom", result)
        self.assertIn("max_contacts=5", result)
        self.assertIn("qualify_frequency=60", result)

    def test_trunk_with_custom_identify_settings_uses_match_header(self):
        trunk = SIPPeer.objects.create(
            name="0001",
            transport=self.transport,
            routing_table=self.routing_table,
            username="0001",
            secret="secret1",
            registrationHere=True,
            custom_identify_settings="match_header=Contact: 0001",
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("; Custom identify settings for 0001", result)
        self.assertIn("type=identify", result)
        self.assertIn("endpoint=0001", result)
        self.assertIn("match_header=Contact: 0001", result)
        self.assertIn("identify_by=header,username", result)

    def test_trunk_without_custom_identify_settings_keeps_default_identify_by(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-default-identify",
            transport=self.transport,
            routing_table=self.routing_table,
            match_hosts="sip.provider.com",
            username="myuser",
            secret="mysecret",
            registrationHere=False,
            registrationThere=False,
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("identify_by=ip", result)
        self.assertNotIn("identify_by=header", result)

    def test_trunk_without_transport_skips_sections(self):
        trunk = SIPPeer.objects.create(
            name="test-trunk-no-transport",
            transport=None,
            routing_table=self.routing_table,
            match_hosts="sip.example.com",
        )
        self.created_peers.append(trunk)
        result = make_pjsip_conf_uplinks()
        self.assertIn("; No transport defined for trunk", result)


class TestMakePjsipConfUsers(TestCase):
    def setUp(self):
        self.transport = SIPTransport.objects.create(
            name="test-user-transport",
            protocol="udp",
            bind="0.0.0.0:5060",
            description="UDP Transport",
        )
        self.routing_table = RoutingTable.objects.get(
            name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )
        self.created_users = []

    def tearDown(self):
        for user in self.created_users:
            user.delete()
        self.transport.delete()

    def test_users_section_header(self):
        result = make_pjsip_conf_users()
        self.assertIn("; ==== Users section ====", result)

    def test_basic_user_userpass_auth(self):
        user = SIPUser.objects.create(
            name="Test John Doe",
            username="test100",
            extension="100",
            secret="password123",
            transport=self.transport,
            routing_table=self.routing_table,
            auth_type="userpass",
        )
        self.created_users.append(user)
        result = make_pjsip_conf_users()
        self.assertIn("; Test John Doe", result)
        self.assertIn("[test100](user-template)", result)
        self.assertIn("transport=test-user-transport", result)
        self.assertIn("auth=test100", result)
        self.assertIn("aors=test100", result)
        self.assertIn("callerid=Test John Doe <100>", result)
        self.assertIn("auth_type = userpass", result)
        self.assertIn("username = test100", result)
        self.assertIn("password = password123", result)

    def test_user_md5_auth(self):
        user = SIPUser.objects.create(
            name="Test Jane Doe",
            username="test101",
            extension="101",
            secret="testpassword",
            transport=self.transport,
            routing_table=self.routing_table,
            auth_type="md5",
        )
        self.created_users.append(user)
        result = make_pjsip_conf_users()
        self.assertIn("auth_type = md5", result)
        self.assertIn("md5_cred =", result)
        self.assertIn("realm =", result)

    def test_user_with_nat(self):
        user = SIPUser.objects.create(
            name="Test NAT User",
            username="test102",
            extension="102",
            secret="pass",
            transport=self.transport,
            routing_table=self.routing_table,
            auth_type="userpass",
            nat=True,
        )
        self.created_users.append(user)
        result = make_pjsip_conf_users()
        self.assertIn("media_use_received_transport=yes", result)
        self.assertIn("rtp_symmetric=yes", result)
        self.assertIn("rewrite_contact=yes", result)
        self.assertIn("force_rport=yes", result)

    def test_user_without_transport_skipped(self):
        user = SIPUser.objects.create(
            name="Test No Transport User",
            username="test103",
            extension="103",
            secret="pass",
            transport=None,
            routing_table=self.routing_table,
        )
        self.created_users.append(user)
        result = make_pjsip_conf_users()
        self.assertNotIn("[test103]", result)


class TestMakePjsipConfTemplates(TestCase):
    def setUp(self):
        Settings.objects.all().delete()

    def test_user_template_empty(self):
        result = make_pjsip_conf_users_template()
        self.assertIn("; ==== Users template ====", result)
        self.assertIn("[user-template](!)", result)

    def test_user_template_with_settings(self):
        Settings.objects.create(user_template="type=endpoint\ndisallow=all\nallow=ulaw")
        result = make_pjsip_conf_users_template()
        self.assertIn("type=endpoint", result)
        self.assertIn("disallow=all", result)

    def test_user_aor_template(self):
        Settings.objects.create(user_aor_template="type=aor\nmax_contacts=1")
        result = make_pjsip_conf_users_aor_template()
        self.assertIn("[user-aor-template](!)", result)
        self.assertIn("type=aor", result)
        self.assertIn("qualify_frequency=30", result)
        self.assertIn("qualify_timeout=5.0", result)

    def test_user_auth_template(self):
        Settings.objects.create(user_auth_template="type=auth")
        result = make_pjsip_conf_users_auth_template()
        self.assertIn("[user-auth-template](!)", result)
        self.assertIn("type=auth", result)


class TestMakePjsipWebrtcTemplates(TestCase):
    def test_wss_transport_with_settings(self):
        transport = SIPTransport.objects.create(
            name="test-wss",
            protocol="wss",
            bind="0.0.0.0:8089",
            description="WebSocket",
        )
        s = Settings.objects.first()
        original_webrtc_template = s.webrtc_template if s else None
        original_webrtc_aor_template = s.webrtc_aor_template if s else None
        original_webrtc_auth_template = s.webrtc_auth_template if s else None

        if s:
            s.webrtc_template = "type=endpoint\nwebrtc=yes"
            s.webrtc_aor_template = "type=aor\nmax_contacts=1"
            s.webrtc_auth_template = "type=auth"
            s.save()
        else:
            s = Settings.objects.create(
                webrtc_template="type=endpoint\nwebrtc=yes",
                webrtc_aor_template="type=aor\nmax_contacts=1",
                webrtc_auth_template="type=auth",
            )
        try:
            result = make_pjsip_webrtc_templates()
            self.assertIn("; ==== WebRTC templates ====", result)
            self.assertIn("[webrtc-template-endpoint](!)", result)
            self.assertIn("webrtc=yes", result)
            self.assertIn("[webrtc-template-aor](!)", result)
            self.assertIn("[webrtc-template-auth](!)", result)
        finally:
            if original_webrtc_template is not None:
                s.webrtc_template = original_webrtc_template
                s.webrtc_aor_template = original_webrtc_aor_template
                s.webrtc_auth_template = original_webrtc_auth_template
                s.save()
            transport.delete()


class TestMakePjsipConf(TestCase):
    def test_full_pjsip_conf_structure(self):
        result = make_pjsip_conf()
        self.assertIn("; === This is auto generated file. Do not edit it! ===", result)
        self.assertIn(";=== Use PearlPBX admin panel! ===", result)
        self.assertIn("; ==== Transports section ====", result)
        self.assertIn("; ==== Uplinks section ====", result)
        self.assertIn("; ==== Users template ====", result)
        self.assertIn("; ==== Users section ====", result)


class TestMakeDialplanExtension(TestCase):
    def setUp(self):
        self.context = DialplanContext.objects.create(
            name="test-context", description="Test Context"
        )

    def test_basic_extension(self):
        ext = DialplanExtension(
            context=self.context,
            ext="100",
            description="Extension 100",
            dialplan="Dial(PJSIP/100,30);",
        )
        result = make_dialplan_extension(ext)
        self.assertIn("// Extension 100", result)
        self.assertIn("100 => {", result)
        self.assertIn("Dial(PJSIP/100,30);", result)
        self.assertIn("}", result)

    def test_multiline_dialplan(self):
        ext = DialplanExtension(
            context=self.context,
            ext="_1XX",
            description="Internal calls",
            dialplan="NoOp(Calling ${EXTEN});\nDial(PJSIP/${EXTEN},30);\nHangup();",
        )
        result = make_dialplan_extension(ext)
        self.assertIn("_1XX => {", result)
        self.assertIn("NoOp(Calling ${EXTEN});", result)
        self.assertIn("Dial(PJSIP/${EXTEN},30);", result)
        self.assertIn("Hangup();", result)


class TestMakeDialplanContexts(TestCase):
    def test_dialplan_contexts_header(self):
        result = make_dialplan_contexts()
        self.assertIn("// ==== Dialplan contexts ====", result)

    def test_context_with_extensions(self):
        ctx = DialplanContext.objects.create(
            name="test-internal", description="Test Internal Context"
        )
        ext1 = DialplanExtension.objects.create(
            context=ctx,
            ext="100",
            description="User 100",
            dialplan="Dial(PJSIP/100);",
        )
        ext2 = DialplanExtension.objects.create(
            context=ctx,
            ext="101",
            description="User 101",
            dialplan="Dial(PJSIP/101);",
        )
        try:
            result = make_dialplan_contexts()
            self.assertIn("// Test Internal Context", result)
            self.assertIn("context test-internal {", result)
            self.assertIn("100 => {", result)
            self.assertIn("101 => {", result)
        finally:
            ext1.delete()
            ext2.delete()
            ctx.delete()


class TestMakeDialplanMacros(TestCase):
    def test_macros_header(self):
        result = make_dialplan_macros()
        self.assertIn("// ==== Macros ====", result)

    def test_basic_macro(self):
        macro = DialplanMacro.objects.create(
            name="test-stdexten",
            description="Standard Extension",
            macro="Dial(PJSIP/${ARG1},30);\nVoicemail(${ARG1});",
        )
        try:
            result = make_dialplan_macros()
            self.assertIn("// Standard Extension", result)
            self.assertIn("macro test-stdexten() {", result)
            self.assertIn("Dial(PJSIP/${ARG1},30);", result)
            self.assertIn("Voicemail(${ARG1});", result)
        finally:
            macro.delete()


class TestMakeDialplanGlobals(TestCase):
    def test_globals_header(self):
        result = make_dialplan_globals()
        self.assertIn("// ==== Global variables ====", result)

    def test_no_globals_block_without_variables(self):
        result = make_dialplan_globals()
        self.assertNotIn("globals {", result)

    def test_globals_with_variables(self):
        v1 = DialplanGlobalVariable.objects.create(
            name="OUTBOUND_CID",
            value="380441234567",
            description="Default outbound CallerID",
        )
        v2 = DialplanGlobalVariable.objects.create(
            name="RECORD_ALL",
            value="yes",
        )
        try:
            result = make_dialplan_globals()
            self.assertIn("globals {", result)
            self.assertIn("// Default outbound CallerID", result)
            self.assertIn("OUTBOUND_CID=380441234567;", result)
            self.assertIn("RECORD_ALL=yes;", result)
            self.assertIn("}\n", result)
            self.assertLess(
                result.index("OUTBOUND_CID"), result.index("RECORD_ALL")
            )
        finally:
            v1.delete()
            v2.delete()


class TestMakeRoutingTables(TestCase):
    def setUp(self):
        self.rt = RoutingTable.objects.get(name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE)
        self.created_contexts = []
        self.created_records = []

    def tearDown(self):
        for record in self.created_records:
            record.delete()
        for ctx in self.created_contexts:
            ctx.delete()

    def test_routing_table_with_records(self):
        ctx1 = DialplanContext.objects.create(
            name="test-route-internal", description="Test internal"
        )
        ctx2 = DialplanContext.objects.create(
            name="test-route-external", description="Test external"
        )
        self.created_contexts.extend([ctx1, ctx2])

        r1 = RoutingRecord.objects.create(
            routing_table=self.rt,
            name="Test Local calls",
            prefix="_199X",
            context=ctx1,
        )
        r2 = RoutingRecord.objects.create(
            routing_table=self.rt,
            name="Test External calls",
            prefix="_099X.",
            context=ctx2,
        )
        self.created_records.extend([r1, r2])
        result = make_routing_tables()
        self.assertIn("// ==== Routing tables ====", result)
        self.assertIn(f"context {self.rt.name} {{", result)
        self.assertIn("// Test Local calls", result)
        self.assertIn("_199X =>", result)
        self.assertIn("// Test External calls", result)
        self.assertIn("_099X. =>", result)


class TestMakeExtensionsAel(TestCase):
    def test_full_ael_structure(self):
        result = make_extensions_ael()
        self.assertIn("// === This is auto generated file. Do not edit it! ===", result)
        self.assertIn("// === Use PearlPBX admin panel! ===", result)
        self.assertIn("// ==== Global variables ====", result)
        self.assertIn("// ==== Macros ====", result)
        self.assertIn("// ==== Routing tables ====", result)
        self.assertIn("// ==== Dialplan contexts ====", result)


class TestMakeManagerConf(TestCase):
    def test_basic_manager_conf(self):
        result = make_manager_conf()
        self.assertIn("; === This is auto generated file. Do not edit it! ===", result)
        self.assertIn("[general]", result)
        self.assertIn("enabled = yes", result)
        self.assertIn("webenabled = yes", result)
        self.assertIn(f"port = {settings.ASTERISK_MANAGER_PORT}", result)
        self.assertIn(f"[{settings.ASTERISK_MANAGER_USERNAME}]", result)
        self.assertIn(f"secret = {settings.ASTERISK_MANAGER_SECRET}", result)

    def test_manager_with_additional_users(self):
        user = ManagerUsers.objects.create(
            username="testwebuser",
            secret="websecret",
            read="call,log",
            write="call",
            permit="192.168.1.0/24",
        )
        try:
            result = make_manager_conf()
            self.assertIn("[testwebuser]", result)
            self.assertIn("secret = websecret", result)
            self.assertIn("read = call,log", result)
            self.assertIn("write = call", result)
            self.assertIn("permit = 192.168.1.0/24", result)
        finally:
            user.delete()


class TestSyncManagerUsersCommand(TestCase):
    def test_creates_service_manager_users(self):
        from django.core.management import call_command

        call_command(
            "sync_manager_users",
            "--callback-secret=callbacksecret",
            "--dashboard-secret=dashboardsecret",
            "--fastagi-secret=fastagisecret",
        )

        callback = ManagerUsers.objects.get(username="callback")
        self.assertEqual(callback.secret, "callbacksecret")
        self.assertEqual(callback.read, "system,call,agent")
        self.assertEqual(callback.write, "system,call,originate")

        dashboard = ManagerUsers.objects.get(username="dashboard_listener")
        self.assertEqual(dashboard.secret, "dashboardsecret")

        fastagi = ManagerUsers.objects.get(username="fastagi")
        self.assertEqual(fastagi.secret, "fastagisecret")

    def test_is_idempotent_and_updates_secret(self):
        from django.core.management import call_command

        call_command(
            "sync_manager_users",
            "--callback-secret=old",
            "--dashboard-secret=old",
            "--fastagi-secret=old",
        )
        call_command(
            "sync_manager_users",
            "--callback-secret=new",
            "--dashboard-secret=new",
            "--fastagi-secret=new",
        )

        self.assertEqual(ManagerUsers.objects.filter(username="callback").count(), 1)
        self.assertEqual(
            ManagerUsers.objects.get(username="callback").secret, "new"
        )


class TestSeedQuickstartCommand(TestCase):
    def test_seeds_queues_ivr_trunk_and_routing(self):
        from django.core.management import call_command

        call_command("seed_quickstart")

        self.assertEqual(Queue.objects.filter(name__in=("Sales", "Support")).count(), 2)
        for queue_name in ("Sales", "Support"):
            members = QueueMember.objects.filter(queue__name=queue_name)
            self.assertEqual(members.count(), 10)
            self.assertNotIn(None, members.values_list("member_name", flat=True))

        self.assertTrue(SIPPeer.objects.filter(name="myprovider").exists())

        self.assertTrue(RoutingTable.objects.filter(name="Incoming").exists())
        self.assertTrue(RoutingTable.objects.filter(name="Outgoing").exists())

        self.assertTrue(DialplanContext.objects.filter(name="ivr-main").exists())
        self.assertTrue(
            DialplanContext.objects.filter(name="quickstart-services").exists()
        )
        self.assertTrue(
            DialplanContext.objects.filter(name="outbound-external").exists()
        )

        self.assertTrue(
            DialplanGlobalVariable.objects.filter(
                name="TRANSFER_CONTEXT", value="Outgoing"
            ).exists()
        )

        outgoing = RoutingTable.objects.get(name="Outgoing")
        self.assertEqual(
            SIPUser.objects.exclude(routing_table=outgoing).count(), 0
        )

        result = make_extensions_ael()
        self.assertIn("context ivr-main {", result)
        self.assertIn("context Outgoing {", result)
        self.assertIn("TRANSFER_CONTEXT=Outgoing;", result)
        # Within the Outgoing routing table, the catch-all _X. outbound record
        # must sort after the more specific _2XX users record, or it would
        # swallow internal calls first.
        # Each routing record renders as "prefix => { goto ctx,${EXTEN},1; }\n"
        # on a single line, so a bare "}\n" also matches mid-block; only the
        # context's own closing brace sits alone on its line, i.e. "\n}\n".
        outgoing_start = result.index("context Outgoing {")
        outgoing_end = result.index("\n}\n", outgoing_start)
        outgoing_block = result[outgoing_start:outgoing_end]
        self.assertLess(
            outgoing_block.index("_2XX =>"), outgoing_block.index("_X. =>")
        )

        queues_conf = make_queues_conf()
        self.assertNotIn(",None,", queues_conf)

        for extension in DialplanExtension.objects.filter(
            context__name__in=("ivr-main", "quickstart-services", "outbound-external")
        ):
            validate_dialplan_field(extension.dialplan)

    def test_is_idempotent(self):
        from django.core.management import call_command

        call_command("seed_quickstart")
        queue_count = Queue.objects.count()
        record_count = RoutingRecord.objects.count()

        call_command("seed_quickstart")

        self.assertEqual(Queue.objects.count(), queue_count)
        self.assertEqual(RoutingRecord.objects.count(), record_count)

    def test_skips_seeding_on_populated_db_without_force(self):
        from django.core.management import call_command

        SIPPeer.objects.create(name="already-there", secret="x")
        call_command("seed_quickstart")

        self.assertFalse(Queue.objects.filter(name="Sales").exists())

    def test_force_seeds_despite_existing_data(self):
        from django.core.management import call_command

        SIPPeer.objects.create(name="already-there", secret="x")
        call_command("seed_quickstart", "--force")

        self.assertTrue(Queue.objects.filter(name="Sales").exists())


class TestExportSipTestAccountsCommand(TestCase):
    def test_voip_provider_peer_uses_contact_or_registration_uri(self):
        import io

        import yaml
        from django.core.management import call_command

        transport = SIPTransport.objects.filter(protocol="udp").first()
        SIPPeer.objects.create(
            name="test-provider",
            username="test",
            secret="secret",
            registrationThere=True,
            registration_uri="reg.example.com:5060",
            contact_uri="sbc.example.com:5061",
            transport=transport,
        )

        out = io.StringIO()
        call_command("export_sip_test_accounts", stdout=out)

        parsed = yaml.safe_load(out.getvalue())
        provider = next(
            a for a in parsed["accounts"] if a["id"] == "test-provider"
        )
        # contact_uri wins over registration_uri when both are set, mirroring
        # core.conf's own AOR-contact precedence.
        self.assertEqual(provider["domain"], "sbc.example.com")
        self.assertEqual(provider["port"], 5061)

    def test_voip_provider_peer_falls_back_to_registration_uri(self):
        import io

        import yaml
        from django.core.management import call_command

        transport = SIPTransport.objects.filter(protocol="udp").first()
        SIPPeer.objects.create(
            name="test-provider-2",
            username="test",
            secret="secret",
            registrationThere=True,
            registration_uri="reg.example.com:5060",
            transport=transport,
        )

        out = io.StringIO()
        call_command("export_sip_test_accounts", stdout=out)

        parsed = yaml.safe_load(out.getvalue())
        provider = next(
            a for a in parsed["accounts"] if a["id"] == "test-provider-2"
        )
        self.assertEqual(provider["domain"], "reg.example.com")
        self.assertEqual(provider["port"], 5060)


class TestMakeQueuesConf(TestCase):
    def test_basic_queues_conf_structure(self):
        result = make_queues_conf()
        self.assertIn("; === This is auto generated file. Do not edit it! ===", result)
        self.assertIn("[general]", result)

    def test_queues_conf_with_global_settings(self):
        gs = CallQueueGlobalSettings.objects.create(
            persistent_members=False,
            autofill=False,
            monitor_type="Monitor",
            shared_lastcall=True,
        )
        try:
            result = make_queues_conf()
            self.assertIn("persistent_members = no", result)
            self.assertIn("autofill = no", result)
            self.assertIn("monitor-type = Monitor", result)
            self.assertIn("shared_lastcall = yes", result)
        finally:
            gs.delete()

    def test_queue_configuration(self):
        moh = MusicOnHold.objects.create(name="test-queue-moh", mode="files")
        ann = QueueAnnouncements.objects.create(name="test-queue-ann")
        queue = Queue.objects.create(
            name="test-support",
            music_class=moh,
            queue_announcement=ann,
            strategy="ringall",
            timeout=30,
            retry=5,
        )
        try:
            result = make_queues_conf()
            self.assertIn("[test-support]", result)
            self.assertIn("strategy=ringall", result)
        finally:
            queue.delete()
            ann.delete()
            moh.delete()

    def test_queue_configuration_emits_previously_ignored_options(self):
        moh = MusicOnHold.objects.create(name="test-queue-moh2", mode="files")
        ann = QueueAnnouncements.objects.create(name="test-queue-ann2")
        queue = Queue.objects.create(
            name="test-support2",
            music_class=moh,
            queue_announcement=ann,
            strategy="ringall",
            timeout=30,
            retry=5,
            maxlen=10,
            weight=5,
            setqueuevar=True,
        )
        try:
            result = make_queues_conf()
            self.assertIn("maxlen=10", result)
            self.assertIn("weight=5", result)
            self.assertIn("setqueuevar=yes", result)
        finally:
            queue.delete()
            ann.delete()
            moh.delete()

    def test_force_longest_waiting_caller_emitted(self):
        gs = CallQueueGlobalSettings.objects.create(
            persistent_members=True,
            autofill=True,
            monitor_type="MixMonitor",
            force_longest_waiting_caller=True,
        )
        try:
            result = make_queues_conf()
            self.assertIn("force_longest_waiting_caller = yes", result)
        finally:
            gs.delete()


class TestMakeQueuerules(TestCase):
    def test_queuerules_structure(self):
        result = make_queuerules_conf()
        self.assertIn("[general]", result)
        self.assertIn("; === This is auto generated file. Do not edit it! ===", result)

    def test_queuerule_with_penalty_changes(self):
        rule = QueueRule.objects.create(name="test-myrule", description="My Test Rule")
        p1 = PenaltyChange.objects.create(
            rule=rule,
            seconds=30,
            max_penalty="5",
            min_penalty="0",
            raise_penalty="0",
            order=1,
        )
        p2 = PenaltyChange.objects.create(
            rule=rule,
            seconds=60,
            max_penalty="10",
            min_penalty="0",
            raise_penalty="0",
            order=2,
        )
        try:
            result = make_queuerules_conf()
            self.assertIn("[test-myrule]", result)
            self.assertIn("; My Test Rule", result)
            self.assertIn("penaltychange => 30,5,0,0", result)
            self.assertIn("penaltychange => 60,10,0,0", result)
        finally:
            p1.delete()
            p2.delete()
            rule.delete()

    def test_relative_penalty_values(self):
        rule = QueueRule.objects.create(name="test-relative")
        p = PenaltyChange.objects.create(
            rule=rule,
            seconds=20,
            max_penalty="+3",
            min_penalty="-1",
            raise_penalty="+2",
            order=0,
        )
        try:
            result = make_queuerules_conf()
            self.assertIn("penaltychange => 20,+3,-1,+2", result)
        finally:
            p.delete()
            rule.delete()

    def test_empty_penalty_values_trimmed(self):
        rule = QueueRule.objects.create(name="test-empty")
        p = PenaltyChange.objects.create(
            rule=rule,
            seconds=10,
            max_penalty="5",
            min_penalty="",
            raise_penalty="",
            order=0,
        )
        try:
            result = make_queuerules_conf()
            self.assertIn("penaltychange => 10,5", result)
            self.assertNotIn("penaltychange => 10,5,", result)
        finally:
            p.delete()
            rule.delete()

    def test_only_seconds_when_all_empty(self):
        rule = QueueRule.objects.create(name="test-allempty")
        p = PenaltyChange.objects.create(
            rule=rule,
            seconds=15,
            max_penalty="",
            min_penalty="",
            raise_penalty="",
            order=0,
        )
        try:
            result = make_queuerules_conf()
            self.assertIn("penaltychange => 15", result)
            self.assertNotIn("penaltychange => 15,", result)
        finally:
            p.delete()
            rule.delete()

    def test_penalty_validator_valid_values(self):
        from core.validators import validate_penalty_value

        for val in ["", "0", "10", "100", "+3", "-2", "+99", "-100"]:
            validate_penalty_value(val)

    def test_penalty_validator_invalid_values(self):
        from core.validators import validate_penalty_value
        from django.core.exceptions import ValidationError

        for val in ["abc", "++3", "10.5", "1000", "+-1"]:
            with self.assertRaises(ValidationError):
                validate_penalty_value(val)


class TestMakeMusiconholdConf(TestCase):
    def test_basic_musiconhold_conf(self):
        result = make_musiconhold_conf()
        self.assertIn("; === This is auto generated file. Do not edit it! ===", result)
        self.assertIn("[general]", result)
        self.assertIn("cachertclasses=yes", result)
        self.assertIn("preferchannelclass=yes", result)

    def test_moh_files_mode(self):
        moh = MusicOnHold.objects.create(
            name="test-default", mode="files", directory="default"
        )
        try:
            result = make_musiconhold_conf()
            self.assertIn("[test-default]", result)
            self.assertIn("mode=files", result)
            self.assertIn("directory=moh/default", result)
        finally:
            moh.delete()

    def test_moh_playlist_mode(self):
        moh = MusicOnHold.objects.create(name="test-custom", mode="playlist")
        entry = MusicOnHoldPlaylistEntry.objects.create(
            moh_class=moh, url="http://stream.example.com/music"
        )
        try:
            result = make_musiconhold_conf()
            self.assertIn("[test-custom]", result)
            self.assertIn("mode=playlist", result)
            self.assertIn("entry=http://stream.example.com/music", result)
        finally:
            entry.delete()
            moh.delete()


class TestAsteriskPatternSpecificity(TestCase):
    def test_literal_extension_highest_priority(self):
        result = _asterisk_pattern_specificity("100")
        self.assertEqual(result[3], 0)

    def test_xbang_lowest_priority(self):
        result = _asterisk_pattern_specificity("_X!")
        self.assertEqual(result, (0, 0, 0, 1))

    def test_fewer_wildcards_higher_priority(self):
        specific = _asterisk_pattern_specificity("_123X")
        general = _asterisk_pattern_specificity("_1XXX")
        self.assertGreater(specific[1], general[1])

    def test_sorting_order(self):
        patterns = ["_X!", "_1XX", "100", "_12X"]
        sorted_patterns = sorted(
            patterns, key=_asterisk_pattern_specificity, reverse=True
        )
        self.assertEqual(sorted_patterns[0], "100")
        self.assertEqual(sorted_patterns[-1], "_X!")


class TestImportMusicOnHoldCommand(TestCase):
    def setUp(self):
        self.sample_config = """[general]
cachertclasses=yes

[default]
mode=files
directory=moh/default
sort=random

[sales-queue]
mode=files
directory=/var/lib/asterisk/moh/sales
sort=alpha

[support]
mode=files
directory=support-music
sort=random
"""

    def test_parse_musiconhold_conf(self):
        from core.management.commands.import_musiconhold import Command

        cmd = Command()
        sections = cmd.parse_musiconhold_conf(self.sample_config)

        self.assertIn("general", sections)
        self.assertIn("default", sections)
        self.assertIn("sales-queue", sections)
        self.assertIn("support", sections)

        self.assertEqual(sections["default"]["mode"], "files")
        self.assertEqual(sections["default"]["directory"], "moh/default")
        self.assertEqual(sections["default"]["sort"], "random")

        self.assertEqual(sections["sales-queue"]["sort"], "alpha")

    def test_normalize_directory(self):
        from core.management.commands.import_musiconhold import Command

        cmd = Command()

        self.assertEqual(cmd.normalize_directory("moh/default"), "default")
        self.assertEqual(
            cmd.normalize_directory("/var/lib/asterisk/moh/sales"), "sales"
        )
        self.assertEqual(cmd.normalize_directory("custom-music"), "custom-music")
        self.assertEqual(cmd.normalize_directory(""), "")
        self.assertEqual(cmd.normalize_directory("moh/sub/dir"), "sub/dir")

    def test_validate_section_valid(self):
        from core.management.commands.import_musiconhold import Command

        cmd = Command()
        error = cmd.validate_section("test-moh", {"mode": "files", "sort": "random"})
        self.assertIsNone(error)

    def test_validate_section_name_too_long(self):
        from core.management.commands.import_musiconhold import Command

        cmd = Command()
        long_name = "a" * 33
        error = cmd.validate_section(long_name, {"mode": "files"})
        self.assertIn("name too long", error)

    def test_validate_section_unsupported_mode(self):
        from core.management.commands.import_musiconhold import Command

        cmd = Command()
        error = cmd.validate_section("test", {"mode": "quietmp3"})
        self.assertIn("unsupported mode", error)

    def test_validate_section_unsupported_sort(self):
        from core.management.commands.import_musiconhold import Command

        cmd = Command()
        error = cmd.validate_section("test", {"mode": "files", "sort": "none"})
        self.assertIn("unsupported sort mode", error)

    def test_import_creates_records(self):
        from io import StringIO
        from django.core.management import call_command

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(self.sample_config)
            temp_path = f.name

        try:
            out = StringIO()
            call_command("import_musiconhold", temp_path, stdout=out)

            self.assertTrue(MusicOnHold.objects.filter(name="default").exists())
            self.assertTrue(MusicOnHold.objects.filter(name="sales-queue").exists())
            self.assertTrue(MusicOnHold.objects.filter(name="support").exists())

            default_moh = MusicOnHold.objects.get(name="default")
            self.assertEqual(default_moh.mode, "files")
            self.assertEqual(default_moh.directory, "default")
            self.assertEqual(default_moh.sort, "random")

            sales_moh = MusicOnHold.objects.get(name="sales-queue")
            self.assertEqual(sales_moh.directory, "sales")
            self.assertEqual(sales_moh.sort, "alpha")

            output = out.getvalue()
            self.assertIn("Imported 3", output)
            self.assertIn("skipped 1", output)
        finally:
            os.unlink(temp_path)
            MusicOnHold.objects.filter(
                name__in=["default", "sales-queue", "support"]
            ).delete()

    def test_dry_run_does_not_create_records(self):
        from io import StringIO
        from django.core.management import call_command

        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(self.sample_config)
            temp_path = f.name

        try:
            out = StringIO()
            call_command("import_musiconhold", temp_path, "--dry-run", stdout=out)

            self.assertFalse(MusicOnHold.objects.filter(name="default").exists())
            self.assertFalse(MusicOnHold.objects.filter(name="sales-queue").exists())

            output = out.getvalue()
            self.assertIn("DRY RUN", output)
            self.assertIn("Imported 3", output)
        finally:
            os.unlink(temp_path)

    def test_skip_duplicate_entries(self):
        from io import StringIO
        from django.core.management import call_command

        import tempfile
        import os

        MusicOnHold.objects.create(name="default", mode="files", directory="old-dir")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(self.sample_config)
            temp_path = f.name

        try:
            out = StringIO()
            call_command("import_musiconhold", temp_path, stdout=out)

            output = out.getvalue()
            self.assertIn("skipped 2", output)
            self.assertIn("already exists", output)

            default_moh = MusicOnHold.objects.get(name="default")
            self.assertEqual(default_moh.directory, "old-dir")
        finally:
            os.unlink(temp_path)
            MusicOnHold.objects.filter(
                name__in=["default", "sales-queue", "support"]
            ).delete()

    def test_file_not_found_error(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError) as context:
            call_command("import_musiconhold", "/nonexistent/file.conf")

        self.assertIn("does not exist", str(context.exception))

    def test_parse_comments_and_empty_lines(self):
        from core.management.commands.import_musiconhold import Command

        config_with_comments = """
; This is a comment
# This is also a comment

[test-section]
; Comment inside section
mode=files
directory=test
"""
        cmd = Command()
        sections = cmd.parse_musiconhold_conf(config_with_comments)

        self.assertEqual(len(sections), 1)
        self.assertIn("test-section", sections)


class TestValidateAsteriskExtensionPrefix(TestCase):
    def test_special_extension_s_is_valid(self):
        from core.validators import validate_asterisk_extension_prefix
        from django.core.exceptions import ValidationError

        try:
            validate_asterisk_extension_prefix("s")
        except ValidationError:
            self.fail(
                "validate_asterisk_extension_prefix raised ValidationError for 's'"
            )

    def test_special_extension_t_is_valid(self):
        from core.validators import validate_asterisk_extension_prefix
        from django.core.exceptions import ValidationError

        try:
            validate_asterisk_extension_prefix("t")
        except ValidationError:
            self.fail(
                "validate_asterisk_extension_prefix raised ValidationError for 't'"
            )

    def test_special_extension_i_is_valid(self):
        from core.validators import validate_asterisk_extension_prefix
        from django.core.exceptions import ValidationError

        try:
            validate_asterisk_extension_prefix("i")
        except ValidationError:
            self.fail(
                "validate_asterisk_extension_prefix raised ValidationError for 'i'"
            )

    def test_special_extension_h_is_valid(self):
        from core.validators import validate_asterisk_extension_prefix
        from django.core.exceptions import ValidationError

        try:
            validate_asterisk_extension_prefix("h")
        except ValidationError:
            self.fail(
                "validate_asterisk_extension_prefix raised ValidationError for 'h'"
            )


class TestValidateAelVariableName(TestCase):
    def test_valid_name(self):
        from core.validators import validate_ael_variable_name
        from django.core.exceptions import ValidationError

        try:
            validate_ael_variable_name("OUTBOUND_CID")
        except ValidationError:
            self.fail("validate_ael_variable_name raised ValidationError for 'OUTBOUND_CID'")

    def test_name_starting_with_digit_is_invalid(self):
        from core.validators import validate_ael_variable_name
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_ael_variable_name("1CID")

    def test_name_with_hyphen_is_invalid(self):
        from core.validators import validate_ael_variable_name
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_ael_variable_name("my-var")


class TestValidateAelVariableValue(TestCase):
    def test_plain_value_is_valid(self):
        from core.validators import validate_ael_variable_value
        from django.core.exceptions import ValidationError

        try:
            validate_ael_variable_value("380441234567")
        except ValidationError:
            self.fail("validate_ael_variable_value raised ValidationError for '380441234567'")

    def test_substitution_value_is_valid(self):
        from core.validators import validate_ael_variable_value
        from django.core.exceptions import ValidationError

        try:
            validate_ael_variable_value("${CALLERID(num)}")
        except ValidationError:
            self.fail("validate_ael_variable_value raised ValidationError for '${CALLERID(num)}'")

    def test_channel_value_is_valid(self):
        from core.validators import validate_ael_variable_value
        from django.core.exceptions import ValidationError

        try:
            validate_ael_variable_value("PJSIP/trunk1")
        except ValidationError:
            self.fail("validate_ael_variable_value raised ValidationError for 'PJSIP/trunk1'")

    def test_value_with_semicolon_is_invalid(self):
        from core.validators import validate_ael_variable_value
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_ael_variable_value("foo; bar")

    def test_value_with_newline_is_invalid(self):
        from core.validators import validate_ael_variable_value
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            validate_ael_variable_value("foo\nbar")


class TestNormalizePhone(TestCase):
    """Tests for core.utils.normalize_phone with default Ukraine settings."""

    def _n(self, phone):
        from core.utils import normalize_phone
        return normalize_phone(phone)

    # --- already correct 10-digit local format ---
    def test_10digit_passthrough(self):
        self.assertEqual(self._n("0671234567"), "0671234567")

    def test_10digit_passthrough_operator_50(self):
        self.assertEqual(self._n("0501234567"), "0501234567")

    # --- E.164 with plus ---
    def test_e164_plus_380(self):
        self.assertEqual(self._n("+380671234567"), "0671234567")

    def test_e164_plus_380_operator_50(self):
        self.assertEqual(self._n("+380501234567"), "0501234567")

    # --- country code without plus ---
    def test_380_prefix_no_plus(self):
        self.assertEqual(self._n("380671234567"), "0671234567")

    def test_380_prefix_no_plus_operator_50(self):
        self.assertEqual(self._n("380501234567"), "0501234567")

    # --- 9-digit (missing leading zero) ---
    def test_9digit_prepend_zero(self):
        self.assertEqual(self._n("671234567"), "0671234567")

    def test_9digit_prepend_zero_operator_50(self):
        self.assertEqual(self._n("501234567"), "0501234567")

    # --- 7-digit city code (Kyiv local) ---
    def test_7digit_kyiv_citycode(self):
        self.assertEqual(self._n("4441234"), "0444441234")

    def test_7digit_citycode_another(self):
        self.assertEqual(self._n("2345678"), "0442345678")

    # --- internal short extensions --- must pass through unchanged ---
    def test_internal_3digit(self):
        self.assertEqual(self._n("101"), "101")

    def test_internal_3digit_200(self):
        self.assertEqual(self._n("223"), "223")

    # --- non-digit characters stripped ---
    def test_formatted_with_dashes(self):
        self.assertEqual(self._n("067-123-45-67"), "0671234567")

    def test_formatted_with_spaces(self):
        self.assertEqual(self._n("067 123 4567"), "0671234567")

    def test_e164_with_spaces(self):
        self.assertEqual(self._n("+38 067 123 4567"), "0671234567")

    # --- edge cases ---
    def test_empty_string(self):
        self.assertEqual(self._n(""), "")

    def test_none_like_empty(self):
        self.assertEqual(self._n(None), None)

    def test_no_digits(self):
        self.assertEqual(self._n("---"), "---")


class TestSIPUserQueueMemberCleanup(TestCase):
    def setUp(self):
        self.transport = SIPTransport.objects.create(
            name="test-qmcleanup-transport", protocol="udp", bind="0.0.0.0:5070"
        )
        self.routing_table = RoutingTable.objects.get(
            name=settings.PEARLPBX_DEFAULT_ROUTING_TABLE
        )
        self.moh = MusicOnHold.objects.create(name="test-qmcleanup-moh")
        self.ann = QueueAnnouncements.objects.create(name="test-qmcleanup-ann")
        self.queue = Queue.objects.create(
            name="TestQMCleanupQueue", music_class=self.moh, queue_announcement=self.ann
        )

    def tearDown(self):
        QueueMember.objects.filter(queue=self.queue).delete()
        self.queue.delete()
        self.ann.delete()
        self.moh.delete()
        SIPUser.objects.filter(transport=self.transport).delete()
        self.transport.delete()

    def test_delete_removes_queue_member(self):
        user = SIPUser.objects.create(
            name="QM Cleanup",
            username="qmcleanup900",
            extension="900",
            secret="x",
            transport=self.transport,
            routing_table=self.routing_table,
        )
        QueueMember.objects.create(
            queue=self.queue, interface=user.standard_pjsip_user, member_name=user.name
        )
        user.delete()
        self.assertFalse(
            QueueMember.objects.filter(interface="PJSIP/qmcleanup900").exists()
        )

    def test_delete_does_not_touch_member_matching_a_sippeer_name(self):
        # Edge case: a SIPPeer sharing the deleted SIPUser's username collapses
        # to the same PJSIP endpoint — the cleanup must not remove that member.
        peer = SIPPeer.objects.create(name="qmcleanup901", transport=self.transport)
        user = SIPUser.objects.create(
            name="QM Cleanup 2",
            username="qmcleanup901",
            extension="901",
            secret="x",
            transport=self.transport,
            routing_table=self.routing_table,
        )
        QueueMember.objects.create(
            queue=self.queue, interface="PJSIP/qmcleanup901", member_name="peer member"
        )
        user.delete()
        self.assertTrue(
            QueueMember.objects.filter(interface="PJSIP/qmcleanup901").exists()
        )
        peer.delete()

    def test_delete_leaves_unrelated_members_alone(self):
        user = SIPUser.objects.create(
            name="QM Cleanup 3",
            username="qmcleanup902",
            extension="902",
            secret="x",
            transport=self.transport,
            routing_table=self.routing_table,
        )
        other = QueueMember.objects.create(
            queue=self.queue, interface="PJSIP/unrelated900", member_name="Unrelated"
        )
        user.delete()
        self.assertTrue(QueueMember.objects.filter(pk=other.pk).exists())


class TestCleanupOrphanQueueMembersCommand(TestCase):
    def setUp(self):
        self.moh = MusicOnHold.objects.create(name="test-cleanup-cmd-moh")
        self.ann = QueueAnnouncements.objects.create(name="test-cleanup-cmd-ann")
        self.queue = Queue.objects.create(
            name="TestCleanupCmdQueue", music_class=self.moh, queue_announcement=self.ann
        )

    def tearDown(self):
        QueueMember.objects.filter(queue=self.queue).delete()
        self.queue.delete()
        self.ann.delete()
        self.moh.delete()

    def test_dry_run_does_not_delete(self):
        from django.core.management import call_command

        orphan = QueueMember.objects.create(
            queue=self.queue, interface="PJSIP/no-such-user", member_name="Ghost"
        )
        call_command("cleanup_orphan_queue_members", "--dry-run")
        self.assertTrue(QueueMember.objects.filter(pk=orphan.pk).exists())

    def test_removes_orphaned_member(self):
        from django.core.management import call_command

        orphan = QueueMember.objects.create(
            queue=self.queue, interface="PJSIP/no-such-user", member_name="Ghost"
        )
        call_command("cleanup_orphan_queue_members")
        self.assertFalse(QueueMember.objects.filter(pk=orphan.pk).exists())

    def test_does_not_remove_member_matching_sippeer(self):
        from django.core.management import call_command

        peer = SIPPeer.objects.create(name="test-cleanup-cmd-peer")
        member = QueueMember.objects.create(
            queue=self.queue, interface="PJSIP/test-cleanup-cmd-peer", member_name="Peer"
        )
        call_command("cleanup_orphan_queue_members")
        self.assertTrue(QueueMember.objects.filter(pk=member.pk).exists())
        peer.delete()


class TestTrunkGroupDialplanGuard(TestCase):
    def setUp(self):
        self.context = DialplanContext.objects.create(name="test-tg-context")

    def tearDown(self):
        DialplanExtension.objects.filter(context=self.context).delete()
        self.context.delete()
        DialplanMacro.objects.filter(name="test_tg_macro").delete()
        TrunkGroup.objects.filter(name__startswith="test-tg-").delete()

    def _make_referencing_extension(self, group_name):
        return DialplanExtension.objects.create(
            context=self.context,
            ext="100",
            dialplan=f"AGI(agi://127.0.0.1:4573/dial-trunk-group,{group_name},${{EXTEN}});",
        )

    def test_find_dialplan_references_matches_extension(self):
        self._make_referencing_extension("test-tg-referenced")
        refs = TrunkGroup.find_dialplan_references("test-tg-referenced")
        self.assertEqual(len(refs), 1)

    def test_find_dialplan_references_matches_macro(self):
        DialplanMacro.objects.create(
            name="test_tg_macro",
            macro="AGI(agi://127.0.0.1:4573/dial-trunk-group,test-tg-macro-ref,${EXTEN});",
        )
        refs = TrunkGroup.find_dialplan_references("test-tg-macro-ref")
        self.assertEqual(len(refs), 1)

    def test_find_dialplan_references_no_false_positive_on_substring(self):
        # "test-tg-ref" is a substring of "test-tg-referenced" but not the
        # literal argument to dial-trunk-group — must not match.
        self._make_referencing_extension("test-tg-referenced")
        refs = TrunkGroup.find_dialplan_references("test-tg-ref")
        self.assertEqual(refs, [])

    def test_rename_blocked_while_referenced(self):
        from django.core.exceptions import ValidationError

        self._make_referencing_extension("test-tg-old-name")
        group = TrunkGroup.objects.create(name="test-tg-old-name")
        group.name = "test-tg-new-name"
        with self.assertRaises(ValidationError):
            group.full_clean()

    def test_rename_allowed_once_reference_removed(self):
        ext = self._make_referencing_extension("test-tg-old-name2")
        group = TrunkGroup.objects.create(name="test-tg-old-name2")
        ext.delete()
        group.name = "test-tg-new-name2"
        group.full_clean()  # must not raise
        group.save()
        self.assertEqual(TrunkGroup.objects.get(pk=group.pk).name, "test-tg-new-name2")

    def test_delete_blocked_while_referenced(self):
        from django.core.exceptions import ValidationError

        self._make_referencing_extension("test-tg-delete-me")
        group = TrunkGroup.objects.create(name="test-tg-delete-me")
        with self.assertRaises(ValidationError):
            group.delete()
        self.assertTrue(TrunkGroup.objects.filter(pk=group.pk).exists())

    def test_delete_allowed_once_reference_removed(self):
        ext = self._make_referencing_extension("test-tg-delete-ok")
        group = TrunkGroup.objects.create(name="test-tg-delete-ok")
        ext.delete()
        group.delete()  # must not raise
        self.assertFalse(TrunkGroup.objects.filter(pk=group.pk).exists())

    def test_admin_hides_delete_button_while_referenced(self):
        from core.admin import TrunkGroupAdmin
        from django.contrib.admin.sites import AdminSite

        self._make_referencing_extension("test-tg-admin-guard")
        group = TrunkGroup.objects.create(name="test-tg-admin-guard")
        admin_instance = TrunkGroupAdmin(TrunkGroup, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(None, obj=group))

    def test_admin_has_delete_permission_checked_per_object_for_bulk_delete(self):
        # Django's own "Delete selected" action calls has_delete_permission()
        # per selected object (via get_deleted_objects()) and refuses the
        # whole batch if any one fails — verify our override still returns
        # True for an unreferenced object alongside a blocked one.
        from unittest.mock import MagicMock

        from core.admin import TrunkGroupAdmin
        from django.contrib.admin.sites import AdminSite

        self._make_referencing_extension("test-tg-bulk-blocked")
        blocked = TrunkGroup.objects.create(name="test-tg-bulk-blocked")
        allowed = TrunkGroup.objects.create(name="test-tg-bulk-allowed")

        request = MagicMock()
        request.user.has_perm.return_value = True
        admin_instance = TrunkGroupAdmin(TrunkGroup, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(request, obj=blocked))
        self.assertTrue(admin_instance.has_delete_permission(request, obj=allowed))


class TestQueueDialplanGuard(TestCase):
    def setUp(self):
        self.context = DialplanContext.objects.create(name="test-q-context")
        self.moh = MusicOnHold.objects.create(name="test-q-guard-moh")
        self.ann = QueueAnnouncements.objects.create(name="test-q-guard-ann")

    def tearDown(self):
        DialplanExtension.objects.filter(context=self.context).delete()
        self.context.delete()
        DialplanMacro.objects.filter(name="test_q_macro").delete()
        Queue.objects.filter(name__startswith="test-q-").delete()
        self.ann.delete()
        self.moh.delete()

    def _make_queue(self, name):
        return Queue.objects.create(
            name=name, music_class=self.moh, queue_announcement=self.ann
        )

    def _make_referencing_extension(self, queue_name):
        return DialplanExtension.objects.create(
            context=self.context,
            ext="200",
            dialplan=f"Answer();\nQueue({queue_name},tT,,,300);\nHangup();",
        )

    def test_find_dialplan_references_matches_extension(self):
        self._make_referencing_extension("test-q-referenced")
        refs = Queue.find_dialplan_references("test-q-referenced")
        self.assertEqual(len(refs), 1)

    def test_find_dialplan_references_matches_macro(self):
        DialplanMacro.objects.create(
            name="test_q_macro",
            macro="Answer();\nQueue(test-q-macro-ref,tT,,,300);\nHangup();",
        )
        refs = Queue.find_dialplan_references("test-q-macro-ref")
        self.assertEqual(len(refs), 1)

    def test_find_dialplan_references_no_false_positive_on_substring(self):
        # "test-q-ref" is a substring of "test-q-referenced" but not the
        # literal argument to Queue(...) — must not match.
        self._make_referencing_extension("test-q-referenced")
        refs = Queue.find_dialplan_references("test-q-ref")
        self.assertEqual(refs, [])

    def test_find_dialplan_references_is_case_insensitive(self):
        # Unlike TrunkGroup, app_queue looks up the queue name with
        # strcasecmp() — a differently-cased literal really does reach it.
        self._make_referencing_extension("sales")
        refs = Queue.find_dialplan_references("Sales")
        self.assertEqual(len(refs), 1)

    def test_rename_blocked_while_referenced(self):
        from django.core.exceptions import ValidationError

        self._make_referencing_extension("test-q-old-name")
        queue = self._make_queue("test-q-old-name")
        queue.name = "test-q-new-name"
        with self.assertRaises(ValidationError):
            queue.full_clean()

    def test_rename_allowed_once_reference_removed(self):
        ext = self._make_referencing_extension("test-q-old-name2")
        queue = self._make_queue("test-q-old-name2")
        ext.delete()
        queue.name = "test-q-new-name2"
        queue.full_clean()  # must not raise
        queue.save()
        self.assertEqual(Queue.objects.get(pk=queue.pk).name, "test-q-new-name2")

    def test_delete_blocked_while_referenced(self):
        from django.core.exceptions import ValidationError

        self._make_referencing_extension("test-q-delete-me")
        queue = self._make_queue("test-q-delete-me")
        with self.assertRaises(ValidationError):
            queue.delete()
        self.assertTrue(Queue.objects.filter(pk=queue.pk).exists())

    def test_delete_allowed_once_reference_removed(self):
        ext = self._make_referencing_extension("test-q-delete-ok")
        queue = self._make_queue("test-q-delete-ok")
        ext.delete()
        queue.delete()  # must not raise
        self.assertFalse(Queue.objects.filter(pk=queue.pk).exists())

    def test_admin_hides_delete_button_while_referenced(self):
        from core.admin import QueueAdmin
        from django.contrib.admin.sites import AdminSite

        self._make_referencing_extension("test-q-admin-guard")
        queue = self._make_queue("test-q-admin-guard")
        admin_instance = QueueAdmin(Queue, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(None, obj=queue))

    def test_admin_has_delete_permission_checked_per_object_for_bulk_delete(self):
        from unittest.mock import MagicMock

        from core.admin import QueueAdmin
        from django.contrib.admin.sites import AdminSite

        self._make_referencing_extension("test-q-bulk-blocked")
        blocked = self._make_queue("test-q-bulk-blocked")
        allowed = self._make_queue("test-q-bulk-allowed")

        request = MagicMock()
        request.user.has_perm.return_value = True
        admin_instance = QueueAdmin(Queue, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(request, obj=blocked))
        self.assertTrue(admin_instance.has_delete_permission(request, obj=allowed))


class TestRoutingTableWebhookDeleteGuard(TestCase):
    def tearDown(self):
        from apps.webhooks.models import Webhook

        Webhook.objects.filter(name__startswith="test-rt-guard-").delete()
        RoutingTable.objects.filter(name__startswith="test-rt-guard-").delete()

    def test_delete_blocked_while_used_by_webhook(self):
        from django.core.exceptions import ValidationError

        from apps.webhooks.models import Webhook

        rt = RoutingTable.objects.create(name="test-rt-guard-1")
        webhook = Webhook.objects.create(
            name="test-rt-guard-webhook", url="https://example.com/hook"
        )
        webhook.routing_tables.add(rt)

        with self.assertRaises(ValidationError):
            rt.delete()
        self.assertTrue(RoutingTable.objects.filter(pk=rt.pk).exists())

    def test_delete_allowed_once_webhook_detached(self):
        from apps.webhooks.models import Webhook

        rt = RoutingTable.objects.create(name="test-rt-guard-2")
        webhook = Webhook.objects.create(
            name="test-rt-guard-webhook2", url="https://example.com/hook"
        )
        webhook.routing_tables.add(rt)
        webhook.routing_tables.remove(rt)

        rt.delete()  # must not raise
        self.assertFalse(RoutingTable.objects.filter(pk=rt.pk).exists())

    def test_admin_hides_delete_button_while_used_by_webhook(self):
        from core.admin import RoutingTableAdmin
        from django.contrib.admin.sites import AdminSite
        from apps.webhooks.models import Webhook

        rt = RoutingTable.objects.create(name="test-rt-guard-3")
        webhook = Webhook.objects.create(
            name="test-rt-guard-webhook3", url="https://example.com/hook"
        )
        webhook.routing_tables.add(rt)

        admin_instance = RoutingTableAdmin(RoutingTable, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(None, obj=rt))


class TestDialplanMacroGuard(TestCase):
    def setUp(self):
        self.context = DialplanContext.objects.create(name="test-dm-guard-context")

    def tearDown(self):
        DialplanExtension.objects.filter(context=self.context).delete()
        self.context.delete()
        DialplanMacro.objects.filter(name__startswith="test_dm_guard_").delete()
        setting, _ = Settings.objects.get_or_create(pk=1)
        if setting.local_users_dial_template and "test_dm_guard_" in (
            setting.local_users_dial_template
        ):
            setting.local_users_dial_template = ""
            setting.save()

    def _make_referencing_extension(self, macro_name, ext="200"):
        return DialplanExtension.objects.create(
            context=self.context, ext=ext, dialplan=f"&{macro_name}();"
        )

    def test_find_dialplan_references_matches_extension(self):
        self._make_referencing_extension("test_dm_guard_referenced")
        refs = DialplanMacro.find_dialplan_references("test_dm_guard_referenced")
        self.assertEqual(len(refs), 1)

    def test_find_dialplan_references_matches_macro(self):
        DialplanMacro.objects.create(
            name="test_dm_guard_caller",
            macro="&test_dm_guard_callee();",
        )
        refs = DialplanMacro.find_dialplan_references("test_dm_guard_callee")
        self.assertEqual(len(refs), 1)

    def test_find_dialplan_references_matches_settings_dial_template(self):
        setting, _ = Settings.objects.get_or_create(pk=1)
        setting.local_users_dial_template = "&test_dm_guard_settings();"
        setting.save()
        refs = DialplanMacro.find_dialplan_references("test_dm_guard_settings")
        self.assertIn("Settings.local_users_dial_template", refs)

    def test_find_dialplan_references_is_case_sensitive(self):
        # AEL resolves macro calls by exact name, unlike Queue's
        # strcasecmp() lookup — a differently-cased literal must NOT match.
        self._make_referencing_extension("test_dm_guard_sales")
        refs = DialplanMacro.find_dialplan_references("Test_Dm_Guard_Sales")
        self.assertEqual(refs, [])

    def test_rename_blocked_while_referenced(self):
        from django.core.exceptions import ValidationError

        self._make_referencing_extension("test_dm_guard_old_name")
        macro = DialplanMacro.objects.create(
            name="test_dm_guard_old_name", macro="NoOp(hi);"
        )
        macro.name = "test_dm_guard_new_name"
        with self.assertRaises(ValidationError):
            macro.full_clean()

    def test_rename_allowed_once_reference_removed(self):
        ext = self._make_referencing_extension("test_dm_guard_old_name2")
        macro = DialplanMacro.objects.create(
            name="test_dm_guard_old_name2", macro="NoOp(hi);"
        )
        ext.delete()
        macro.name = "test_dm_guard_new_name2"
        macro.full_clean()  # must not raise
        macro.save()
        self.assertEqual(
            DialplanMacro.objects.get(pk=macro.pk).name, "test_dm_guard_new_name2"
        )

    def test_delete_blocked_while_referenced(self):
        from django.core.exceptions import ValidationError

        self._make_referencing_extension("test_dm_guard_delete_me")
        macro = DialplanMacro.objects.create(
            name="test_dm_guard_delete_me", macro="NoOp(hi);"
        )
        with self.assertRaises(ValidationError):
            macro.delete()
        self.assertTrue(DialplanMacro.objects.filter(pk=macro.pk).exists())

    def test_delete_allowed_once_reference_removed(self):
        ext = self._make_referencing_extension("test_dm_guard_delete_ok")
        macro = DialplanMacro.objects.create(
            name="test_dm_guard_delete_ok", macro="NoOp(hi);"
        )
        ext.delete()
        macro.delete()  # must not raise
        self.assertFalse(DialplanMacro.objects.filter(pk=macro.pk).exists())

    def test_admin_hides_delete_button_while_referenced(self):
        from core.admin import DialplanMacroAdmin
        from django.contrib.admin.sites import AdminSite

        self._make_referencing_extension("test_dm_guard_admin")
        macro = DialplanMacro.objects.create(
            name="test_dm_guard_admin", macro="NoOp(hi);"
        )
        admin_instance = DialplanMacroAdmin(DialplanMacro, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(None, obj=macro))

    def test_admin_has_delete_permission_checked_per_object_for_bulk_delete(self):
        from unittest.mock import MagicMock

        from core.admin import DialplanMacroAdmin
        from django.contrib.admin.sites import AdminSite

        self._make_referencing_extension("test_dm_guard_bulk_blocked")
        blocked = DialplanMacro.objects.create(
            name="test_dm_guard_bulk_blocked", macro="NoOp(hi);"
        )
        allowed = DialplanMacro.objects.create(
            name="test_dm_guard_bulk_allowed", macro="NoOp(hi);"
        )

        request = MagicMock()
        request.user.has_perm.return_value = True
        admin_instance = DialplanMacroAdmin(DialplanMacro, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(request, obj=blocked))
        self.assertTrue(admin_instance.has_delete_permission(request, obj=allowed))


class TestDialplanContextGuard(TestCase):
    def tearDown(self):
        from apps.webhooks.models import Webhook

        Webhook.objects.filter(name__startswith="test-dc-guard-").delete()
        DialplanExtension.objects.filter(
            context__name__startswith="test-dc-guard-"
        ).delete()
        DialplanContext.objects.filter(name__startswith="test-dc-guard-").delete()

    def test_extension_in_reserved_context_blocked_at_model_level(self):
        from django.core.exceptions import ValidationError

        ctx, _ = DialplanContext.objects.get_or_create(
            name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD
        )
        ext = DialplanExtension(context=ctx, ext="100", dialplan="Hangup();")
        with self.assertRaises(ValidationError):
            ext.full_clean()

    def test_rename_reserved_context_blocked(self):
        from django.core.exceptions import ValidationError

        ctx, _ = DialplanContext.objects.get_or_create(
            name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD
        )
        ctx.name = "renamed"
        with self.assertRaises(ValidationError):
            ctx.full_clean()

    def test_delete_reserved_context_blocked(self):
        from django.core.exceptions import ValidationError

        ctx, _ = DialplanContext.objects.get_or_create(
            name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD
        )
        with self.assertRaises(ValidationError):
            ctx.delete()
        self.assertTrue(DialplanContext.objects.filter(pk=ctx.pk).exists())

    def test_delete_blocked_while_used_by_webhook(self):
        from django.core.exceptions import ValidationError

        from apps.webhooks.models import Webhook

        ctx = DialplanContext.objects.create(name="test-dc-guard-1")
        webhook = Webhook.objects.create(
            name="test-dc-guard-webhook", url="https://example.com/hook"
        )
        webhook.contexts.add(ctx)

        with self.assertRaises(ValidationError):
            ctx.delete()
        self.assertTrue(DialplanContext.objects.filter(pk=ctx.pk).exists())

    def test_delete_allowed_once_webhook_detached(self):
        from apps.webhooks.models import Webhook

        ctx = DialplanContext.objects.create(name="test-dc-guard-2")
        webhook = Webhook.objects.create(
            name="test-dc-guard-webhook2", url="https://example.com/hook"
        )
        webhook.contexts.add(ctx)
        webhook.contexts.remove(ctx)

        ctx.delete()  # must not raise
        self.assertFalse(DialplanContext.objects.filter(pk=ctx.pk).exists())

    def test_admin_hides_delete_button_for_reserved_context(self):
        from core.admin import DialplanContextAdmin
        from django.contrib.admin.sites import AdminSite

        ctx, _ = DialplanContext.objects.get_or_create(
            name=settings.PEARLPBX_DEFAULT_ROUTING_RECORD
        )
        admin_instance = DialplanContextAdmin(DialplanContext, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(None, obj=ctx))

    def test_admin_hides_delete_button_while_used_by_webhook(self):
        from core.admin import DialplanContextAdmin
        from django.contrib.admin.sites import AdminSite
        from apps.webhooks.models import Webhook

        ctx = DialplanContext.objects.create(name="test-dc-guard-3")
        webhook = Webhook.objects.create(
            name="test-dc-guard-webhook3", url="https://example.com/hook"
        )
        webhook.contexts.add(ctx)

        admin_instance = DialplanContextAdmin(DialplanContext, AdminSite())
        self.assertFalse(admin_instance.has_delete_permission(None, obj=ctx))
