from django.db import migrations


def grant_staff_inventory_request(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    staff_group = Group.objects.get(name='Warehouse Staff')
    perms = Permission.objects.filter(
        codename__in=['add_inventoryrequest', 'view_inventoryrequest'],
        content_type__app_label='inventory',
    )
    for perm in perms:
        staff_group.permissions.add(perm)


def revoke_staff_inventory_request(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    staff_group = Group.objects.get(name='Warehouse Staff')
    perms = Permission.objects.filter(
        codename__in=['add_inventoryrequest', 'view_inventoryrequest'],
        content_type__app_label='inventory',
    )
    for perm in perms:
        staff_group.permissions.remove(perm)


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0011_manual_notes_inventorytransaction'),
    ]

    operations = [
        migrations.RunPython(grant_staff_inventory_request, revoke_staff_inventory_request),
    ]
