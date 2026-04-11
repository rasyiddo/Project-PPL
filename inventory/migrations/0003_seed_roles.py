from django.db import migrations, transaction

ROLE_USERS = {
    'Admin': [
        {'username': 'admin', 'password': 'admin123', 'superuser': True},
    ],
    'Manager': [
        {'username': 'manager1', 'password': 'manager123'},
        {'username': 'manager2', 'password': 'manager123'},
        {'username': 'manager3', 'password': 'manager123'},
    ],
    'Warehouse Staff': [
        {'username': 'staff1', 'password': 'staff123'},
        {'username': 'staff2', 'password': 'staff123'},
        {'username': 'staff3', 'password': 'staff123'},
        {'username': 'staff4', 'password': 'staff123'},
    ],
    'Employee': [
        {'username': 'employee1', 'password': 'employee123'},
        {'username': 'employee2', 'password': 'employee123'},
        {'username': 'employee3', 'password': 'employee123'},
        {'username': 'employee4', 'password': 'employee123'},
    ],
}

def seed_roles(apps, schema_editor):
    with transaction.atomic():
        group_model = apps.get_model('auth', 'Group')
        permission_model = apps.get_model('auth', 'Permission')
        user_model = apps.get_model('auth', 'User')

        # Create Groups
        admin_group, _ = group_model.objects.get_or_create(name='Admin')
        staff_group, _ = group_model.objects.get_or_create(name='Warehouse Staff')
        manager_group, _ = group_model.objects.get_or_create(name='Manager')
        employee_group, _ = group_model.objects.get_or_create(name='Employee')

        # Get Permissions
        all_permissions = permission_model.objects.all()

        # Custom permissions
        approve_inventory = permission_model.objects.filter(codename='approve_inventoryrequest')
        approve_procurement = permission_model.objects.filter(codename='approve_procurementrequest')

        # Model permissions
        product_perms = permission_model.objects.filter(content_type__model='product')
        inventory_request_perms = permission_model.objects.filter(content_type__model='inventoryrequest')
        procurement_request_perms = permission_model.objects.filter(content_type__model='procurementrequest')
        transaction_perms = permission_model.objects.filter(content_type__model='inventorytransaction')

        # Assign Permissions
        # Admin → everything
        admin_group.permissions.set(all_permissions)

        # Manager → approve + view
        manager_group.permissions.set(
            list(product_perms.filter(codename__in=['view_product'])) +
            list(inventory_request_perms) +
            list(procurement_request_perms) +
            list(approve_inventory) +
            list(approve_procurement)
        )

        # Warehouse Staff → handle stock & transactions
        staff_group.permissions.set(
            list(product_perms) +
            list(transaction_perms) +
            list(inventory_request_perms.filter(codename__in=['view_inventoryrequest'])) +
            list(procurement_request_perms.filter(codename__in=['view_procurementrequest']))
        )

        # Employee → create & view own requests
        employee_group.permissions.set(
            list(product_perms.filter(codename__in=['view_product'])) +
            list(inventory_request_perms.filter(codename__in=[
                'add_inventoryrequest',
                'view_inventoryrequest'
            ]))
        )

        # Create Users
        for role_name, users in ROLE_USERS.items():
            group = group_model.objects.get(name=role_name)

            for user_data in users:
                username = user_data['username']
                password = user_data['password']
                is_superuser = user_data.get('superuser', False)

                if not user_model.objects.filter(username=username).exists():
                    if is_superuser:
                        user = user_model.objects.create_superuser(
                            username=username,
                            password=password
                        )
                    else:
                        user = user_model.objects.create_user(
                            username=username,
                            password=password
                        )

                    user.groups.add(group)


def reverse_seed(apps, schema_editor):
    group_model = apps.get_model('auth', 'Group')
    user_model = apps.get_model('auth', 'User')

    role_names = ['Admin', 'Warehouse Staff', 'Manager', 'Employee']

    # Delete users by ROLE_USERS
    usernames = []
    for users in ROLE_USERS.values():
        usernames.extend([u['username'] for u in users])

    user_model.objects.filter(username__in=usernames).delete()
    group_model.objects.filter(name__in=role_names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_seed_permissions'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(seed_roles, reverse_seed),
    ]