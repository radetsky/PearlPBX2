from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import migrations


def add_routing_report_permission(apps, schema_editor):
    content_type = ContentType.objects.get(app_label="auth", model="permission")

    permission, created = Permission.objects.get_or_create(
        codename="view_routing_report",
        defaults={
            "name": "Can view routing table report",
            "content_type": content_type,
        },
    )
    if created:
        print("Created permission: view_routing_report")

    try:
        group = Group.objects.get(name="Report Viewer")
        group.permissions.add(permission)
        print("Assigned view_routing_report to 'Report Viewer' group")
    except Group.DoesNotExist:
        print("Warning: 'Report Viewer' group not found")


def remove_routing_report_permission(apps, schema_editor):
    Permission.objects.filter(codename="view_routing_report").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0061_alter_penaltychange_max_penalty_and_more"),
    ]

    operations = [
        migrations.RunPython(
            add_routing_report_permission,
            remove_routing_report_permission,
        ),
    ]
