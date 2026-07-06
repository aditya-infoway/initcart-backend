# pos/migrations/0057_seed_order_sequence_global.py

import re
from django.db import migrations


def seed_order_sequence(apps, schema_editor):
    BranchOrder = apps.get_model('pos', 'BranchOrder')
    OrderSequence = apps.get_model('pos', 'OrderSequence')

    # Global pattern — branch_code (RVA, DMF, etc.) ho ya na ho, dono match karega,
    # kyunki counter dono cases mein SHARED/global hai (model comment ke hisaab se)
    pattern = re.compile(r'^ORD/(?:[A-Z0-9]+/)?(\d{2}-\d{2})/(\d+)$')
    max_per_fy = {}

    for order in BranchOrder.objects.all():
        m = pattern.match(order.order_id or '')
        if not m:
            continue
        fy = m.group(1)
        num = int(m.group(2))
        if fy not in max_per_fy or num > max_per_fy[fy]:
            max_per_fy[fy] = num

    for fy, max_num in max_per_fy.items():
        OrderSequence.objects.update_or_create(
            financial_year=fy,
            defaults={'last_number': max_num}
        )


def reverse_seed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0056_backfill_sent_quantity'),
    ]

    operations = [
        migrations.RunPython(seed_order_sequence, reverse_seed),
    ]