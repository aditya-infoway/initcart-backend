# pos/management/commands/seed_order_sequence.py
# NEW FILE
#
# ⚠️ IMPORTANT: Yeh command migration (makemigrations + migrate) ke TURANT BAAD,
#    aur naya koi bhi order create hone se PEHLE, ek baar zaroor chalayen:
#
#       python manage.py seed_order_sequence
#
# Yeh purane live BranchOrder data ko scan karke, har financial year ke liye
# OrderSequence.last_number ko sabse bade existing serial number pe set kar deta hai.
# Isse naya order banane par duplicate order_id (IntegrityError) nahi aayega.
#
# Safe hai — dobara bhi chala sakte hain, kabhi bhi (idempotent: hamesha
# correct max hi set karega, purana data ko touch nahi karega).

from django.core.management.base import BaseCommand
from django.db import transaction
from pos.models.branch_order import BranchOrder, OrderSequence


class Command(BaseCommand):
    help = "Seed OrderSequence counters from existing live BranchOrder data (run once after migration)."

    def handle(self, *args, **options):
        fy_max_numbers = {}  # { "26-27": 15, "25-26": 240, ... }

        orders = BranchOrder.objects.exclude(order_id__isnull=True).exclude(order_id="")

        for order in orders.iterator():
            parts = order.order_id.split('/')
            # order_id ke 2 possible shapes ho sakte hain (yeh 2 ALAG-ALAG,
            # unrelated examples hain — sirf format samjhane ke liye,
            # ek dusre ke aage-peeche wale orders NAHI hain):
            #
            #   Bina branch code: "ORD/26-27/0007"        -> ['ORD', '26-27', '0007']
            #   Branch code ke sath: "ORD/UGF/26-27/0012" -> ['ORD', 'UGF', '26-27', '0012']
            #
            # Dono cases mein hamesha parts[-1] hi serial number hota hai,
            # aur parts[-2] hamesha financial year hota hai — isliye parsing
            # branch_code ho ya na ho, dono format ke liye sahi kaam karta hai.
            if len(parts) < 3:
                self.stdout.write(self.style.WARNING(
                    f"Skipping unrecognized order_id format: {order.order_id}"
                ))
                continue

            fy = parts[-2]
            number_str = parts[-1]

            try:
                number = int(number_str)
            except ValueError:
                self.stdout.write(self.style.WARNING(
                    f"Skipping non-numeric serial in order_id: {order.order_id}"
                ))
                continue

            if fy not in fy_max_numbers or number > fy_max_numbers[fy]:
                fy_max_numbers[fy] = number

        if not fy_max_numbers:
            self.stdout.write(self.style.SUCCESS(
                "No existing orders found. Nothing to seed — counters will start fresh at 0001."
            ))
            return

        with transaction.atomic():
            for fy, max_number in fy_max_numbers.items():
                seq, created = OrderSequence.objects.select_for_update().get_or_create(
                    financial_year=fy,
                    defaults={'last_number': max_number},
                )
                if not created and seq.last_number < max_number:
                    seq.last_number = max_number
                    seq.save(update_fields=['last_number'])

                action = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(
                    f"{action} OrderSequence for FY {fy} → last_number = {max_number}"
                ))

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Done. Next order in each FY will continue correctly from the seeded number."
        ))