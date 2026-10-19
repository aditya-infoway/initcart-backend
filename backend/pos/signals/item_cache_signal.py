from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from pos.models.items import items, itemvariants
from pos.utils.item_cache import bump_items_version


@receiver([post_save, post_delete], sender=items)
def item_changed(sender, instance, **kwargs):
    branch_id = getattr(instance, "branch_id", None)
    if branch_id:
        transaction.on_commit(lambda: bump_items_version(branch_id))


@receiver([post_save, post_delete], sender=itemvariants)
def variant_changed(sender, instance, **kwargs):
    try:
        branch_id = instance.item.branch_id
    except Exception:
        return
    if branch_id:
        transaction.on_commit(lambda: bump_items_version(branch_id))