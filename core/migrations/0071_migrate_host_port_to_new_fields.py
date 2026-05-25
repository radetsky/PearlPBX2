from django.db import migrations


def migrate_host_port(apps, schema_editor):
    SIPPeer = apps.get_model("core", "SIPPeer")
    for peer in SIPPeer.objects.exclude(host_port="").exclude(host_port__isnull=True):
        hosts = [h.strip() for h in peer.host_port.split(",") if h.strip()]
        if not hosts:
            continue
        if not peer.match_hosts:
            peer.match_hosts = ", ".join(h.split(":")[0] for h in hosts)
        if not peer.contact_uri:
            peer.contact_uri = hosts[0]
        if not peer.registration_uri:
            peer.registration_uri = hosts[0]
        peer.save()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0070_add_registration_contact_match_hosts_to_sippeer"),
    ]

    operations = [
        migrations.RunPython(migrate_host_port, migrations.RunPython.noop),
    ]
