# Generated merge migration to resolve conflicting 0026 migrations
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0026_add_order_email'),
        ('shop', '0026_order_email'),
    ]

    operations = [
    ]
