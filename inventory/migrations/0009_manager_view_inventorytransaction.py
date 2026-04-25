from django.db import migrations


def add_permission(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    manager_group = Group.objects.get(name='Manager')
    perm = Permission.objects.get(codename='view_inventorytransaction')
    manager_group.permissions.add(perm)


def remove_permission(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    manager_group = Group.objects.get(name='Manager')
    perm = Permission.objects.get(codename='view_inventorytransaction')
    manager_group.permissions.remove(perm)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_procurementrequest_price_notes'),
    ]

    operations = [
        migrations.RunPython(add_permission, reverse_code=remove_permission),
    ]
