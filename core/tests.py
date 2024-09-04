from django.test import TestCase
from core.models import SIPTransport


class TestSIPTransport(TestCase):
    def setUp(self) -> None:
        SIPTransport.objects.create(
            bind='0.0.0.0',
            protocol='udp',
            name='udp-transport',
            description='UDP transport'
        )
        SIPTransport.objects.create(
            bind='0.0.0.0',
            protocol='tcp',
            name='tcp-transport',
            description='TCP transport'
        )
        SIPTransport.objects.create(
            bind='0.0.0.0',
            protocol='tls',
            name='tls-transport',
            description='TLS transport'
        )
        SIPTransport.objects.create(
            protocol='wss',
            name='wss-transport',
            description='WebSocket secure transport'
        )

    def test_sip_transports_exist(self):
        udp_transport = SIPTransport.objects.get(name='udp-transport')
        self.assertEqual(udp_transport.protocol, 'udp')
        tcp_transport = SIPTransport.objects.get(name='tcp-transport')
        self.assertEqual(tcp_transport.protocol, 'tcp')
        tls_transport = SIPTransport.objects.get(name='tls-transport')
        self.assertEqual(tls_transport.protocol, 'tls')
        wss_transport = SIPTransport.objects.get(name='wss-transport')
        self.assertEqual(wss_transport.protocol, 'wss')
