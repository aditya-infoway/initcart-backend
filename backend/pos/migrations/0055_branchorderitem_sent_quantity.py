# pos/migrations/0055_branchorderitem_sent_quantity.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0054_returnsequence'),   # 👈 apni last migration ka exact naam yahan daalo
    ]

    operations = [
        migrations.AddField(
            model_name='branchorderitem',
            name='sent_quantity',
            field=models.IntegerField(default=0),
        ),
    ]