from django.db import migrations, transaction


def move_add_procurementrequest_to_warehouse_staff(apps, schema_editor):
    with transaction.atomic():
        Group = apps.get_model('auth', 'Group')
        Permission = apps.get_model('auth', 'Permission')

        manager_group = Group.objects.get(name='Manager')
        staff_group = Group.objects.get(name='Warehouse Staff')
        add_procurement_permission = Permission.objects.get(codename='add_procurementrequest')

        manager_group.permissions.remove(add_procurement_permission)
        staff_group.permissions.add(add_procurement_permission)


def reverse_move_add_procurementrequest_to_warehouse_staff(apps, schema_editor):
    with transaction.atomic():
        Group = apps.get_model('auth', 'Group')
        Permission = apps.get_model('auth', 'Permission')

        manager_group = Group.objects.get(name='Manager')
        staff_group = Group.objects.get(name='Warehouse Staff')
        add_procurement_permission = Permission.objects.get(codename='add_procurementrequest')

        staff_group.permissions.remove(add_procurement_permission)
        manager_group.permissions.add(add_procurement_permission)


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_inventoryrequest_reason'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(
            move_add_procurementrequest_to_warehouse_staff,
            reverse_move_add_procurementrequest_to_warehouse_staff,
        ),
    ]
