from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import migrations


def add_lists_permissions(apps, schema_editor):
    content_type = ContentType.objects.get(app_label="auth", model="permission")

    permissions_data = [
        ("edit_blocklist", "Can edit blocklist entries"),
        ("edit_allowlist", "Can edit allowlist entries"),
        ("edit_contacts", "Can edit contacts"),
    ]

    created_permissions = []
    for codename, name in permissions_data:
        permission, created = Permission.objects.get_or_create(
            codename=codename,
            defaults={"name": name, "content_type": content_type},
        )
        if created:
            print(f"Created permission: {codename}")
        created_permissions.append(permission)

    try:
        group = Group.objects.get(name="Report Viewer")
        for perm in created_permissions:
            group.permissions.add(perm)
        print("Assigned lists permissions to 'Report Viewer' group")
    except Group.DoesNotExist:
        print("Warning: 'Report Viewer' group not found")


def remove_lists_permissions(apps, schema_editor):
    Permission.objects.filter(
        codename__in=["edit_blocklist", "edit_allowlist", "edit_contacts"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0062_add_routing_report_permission"),
    ]

    operations = [
        migrations.RunPython(
            add_lists_permissions,
            remove_lists_permissions,
        ),
    ]
