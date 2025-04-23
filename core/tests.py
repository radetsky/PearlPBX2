from django.conf import settings
from django.test import TestCase
from core.models import SIPTransport, RoutingTable
from core.utils import create_directory, remove_directory


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

class TestApplyToFileSystem(TestCase):
    def test_create_directory(self):
        # Test creating a directory
        create_directory("/tmp")
        create_directory("/tmp/etc/asterisk")
        self.assertRaises(OSError, create_directory, "/etc/asterisk")

    def test_remove_directory(self):
        remove_directory("/tmp/etc/asterisk")
        self.assertRaises(OSError, remove_directory, "/etc/asterisk")
