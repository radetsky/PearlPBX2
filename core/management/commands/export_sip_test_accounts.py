import yaml
from django.core.management.base import BaseCommand

from core.models import Settings, SIPPeer, SIPUser


class Command(BaseCommand):
    help = "Export SIP accounts to YAML format for SIP Test Agent"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="-",
            help="Output file path, use '-' for stdout (default: stdout)",
        )
        parser.add_argument(
            "--domain",
            type=str,
            default=None,
            help="PBX domain/IP address (default: from Settings model)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=5060,
            help="PBX SIP port (default: 5060)",
        )
        parser.add_argument(
            "--local-port-base",
            type=int,
            default=5070,
            help="Starting local port for SIP Test Agent (default: 5070)",
        )
        parser.add_argument(
            "--port-step",
            type=int,
            default=2,
            help="Port increment between accounts (default: 2)",
        )

    def handle(self, *args, **kwargs):
        output = kwargs["output"]
        pbx_port = kwargs["port"]
        local_port = kwargs["local_port_base"]
        port_step = kwargs["port_step"]

        domain = kwargs["domain"]
        if not domain:
            settings_obj = Settings.objects.first()
            domain = settings_obj.domain if settings_obj else "127.0.0.1"

        accounts = []

        for peer in SIPPeer.objects.select_related("transport", "routing_table").order_by("name"):
            if peer.registrationHere:
                account = self._build_gsm_gateway(peer, domain, pbx_port, local_port)
            elif peer.registrationThere:
                account = self._build_voip_provider(peer, domain, pbx_port, local_port)
            else:
                self.stderr.write(f"Skipping peer '{peer.name}': neither registrationHere nor registrationThere")
                continue

            dest_numbers = self._get_dest_numbers(peer.routing_table)
            if dest_numbers:
                account["destination_numbers"] = dest_numbers

            accounts.append(account)
            local_port += port_step

        for user in SIPUser.objects.select_related("routing_table").order_by("username"):
            account = {
                "id": user.username,
                "type": "telephone",
                "username": user.username,
                "password": user.secret,
                "domain": domain,
                "port": pbx_port,
                "local_port": local_port,
                "caller_id": user.extension or user.username,
            }

            dest_numbers = self._get_dest_numbers(user.routing_table)
            if dest_numbers:
                account["destination_numbers"] = dest_numbers

            accounts.append(account)
            local_port += port_step

        yaml_content = yaml.dump(
            {"accounts": accounts},
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        if output == "-":
            self.stdout.write(yaml_content)
        else:
            with open(output, "w") as f:
                f.write(yaml_content)
            self.stderr.write(self.style.SUCCESS(f"Exported {len(accounts)} accounts to {output}"))

    def _build_gsm_gateway(self, peer, domain, pbx_port, local_port):
        account = {"id": peer.name, "type": "gsm_gateway"}
        if peer.username:
            account["username"] = peer.username
        if peer.secret:
            account["password"] = peer.secret
        account["domain"] = domain
        account["port"] = pbx_port
        account["local_port"] = local_port
        account["caller_id"] = "UA"
        return account

    def _build_voip_provider(self, peer, domain, pbx_port, local_port):
        account = {"id": peer.name, "type": "voip_provider"}

        if peer.host_port:
            parts = peer.host_port.strip().split(":")
            account["domain"] = parts[0].strip()
            account["port"] = int(parts[1]) if len(parts) > 1 else pbx_port
        else:
            account["domain"] = domain
            account["port"] = pbx_port

        if peer.transport and peer.transport.external_signaling_address:
            account["external_ip"] = str(peer.transport.external_signaling_address)

        account["local_port"] = local_port
        account["caller_id"] = "UA"
        return account

    def _get_dest_numbers(self, routing_table):
        if not routing_table:
            return []
        return [
            record.prefix
            for record in routing_table.routing_records.all()
            if not record.prefix.startswith("_")
        ]
