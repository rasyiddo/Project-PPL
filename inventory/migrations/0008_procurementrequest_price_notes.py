from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_move_add_procurementrequest_to_warehouse_staff'),
    ]

    operations = [
        migrations.AddField(
            model_name='procurementrequest',
            name='notes',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='procurementrequest',
            name='price',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
