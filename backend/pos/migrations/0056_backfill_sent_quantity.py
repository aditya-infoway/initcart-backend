# pos/migrations/0056_backfill_sent_quantity.py  (FINAL — ye use karna)

from django.db import migrations
from django.db.models import Sum


def backfill_sent_quantity(apps, schema_editor):
    BranchOrderItem = apps.get_model('pos', 'BranchOrderItem')
    StockTransfer = apps.get_model('pos', 'StockTransfer')
    StockTransferItem = apps.get_model('pos', 'StockTransferItem')
    BranchOrder = apps.get_model('pos', 'BranchOrder')

    order_ids = (
        StockTransfer.objects
        .filter(transfer_type='order', source_order__isnull=False)
        .values_list('source_order_id', flat=True)
        .distinct()
    )

    for order_id in order_ids:
        transfer_ids = StockTransfer.objects.filter(
            transfer_type='order', source_order_id=order_id
        ).values_list('id', flat=True)

        dispatched = (
            StockTransferItem.objects
            .filter(transfer_id__in=transfer_ids)
            .values('from_variant_id')
            .annotate(total_sent=Sum('quantity'))
        )
        dispatched_map = {d['from_variant_id']: (d['total_sent'] or 0) for d in dispatched}

        for item in BranchOrderItem.objects.filter(order_id=order_id):
            sent = dispatched_map.get(item.source_variant_id, 0)
            sent = min(sent, item.requested_quantity)
            item.sent_quantity = sent
            item.is_transferred = sent >= item.requested_quantity
            item.save(update_fields=['sent_quantity', 'is_transferred'])

    # Extra safety net: order status already 'sent' hai (fully complete tha)
    # lekin kisi edge-case se item ka sent_quantity poora match nahi hua —
    # use bhi fully-sent maan lo taaki dubara accidentally process na ho.
    for order in BranchOrder.objects.filter(status='sent'):
        for item in order.items.all():
            if not item.is_removed_by_admin and (item.sent_quantity or 0) < item.requested_quantity:
                item.sent_quantity = item.requested_quantity
                item.is_transferred = True
                item.save(update_fields=['sent_quantity', 'is_transferred'])


def reverse_backfill(apps, schema_editor):
    pass  # sent_quantity ko 0 karna data loss hoga, isliye reverse no-op


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0055_branchorderitem_sent_quantity'),
    ]

    operations = [
        migrations.RunPython(backfill_sent_quantity, reverse_backfill),
    ]