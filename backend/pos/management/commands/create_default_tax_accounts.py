# pos/management/commands/create_default_tax_accounts.py
from django.core.management.base import BaseCommand
from pos.models.branch import Branch
from pos.utils.default_tax_accounts import ensure_default_tax_accounts


class Command(BaseCommand):
    help = "Sab existing branches ke liye 6 default tax accounts banata hai"

    def handle(self, *args, **opts):
        for b in Branch.objects.all():
            ensure_default_tax_accounts(b, created_by=getattr(b, "created_by", None))
            self.stdout.write(f"✓ {b.branch_name}")