# pos/management/commands/seed_return_sequence.py
# NEW FILE
#
# ⚠️ IMPORTANT: Yeh command migration (makemigrations + migrate) ke TURANT BAAD,
#    aur naya koi bhi return create hone se PEHLE, ek baar zaroor chalayen:
#
#       python manage.py seed_return_sequence
#
# Yeh purane live StockReturn data ko scan karke, har financial year ke liye
# ReturnSequence.last_number ko sabse bade existing serial number pe set kar
# deta hai. Isse naya return banane par duplicate return_no (IntegrityError)
# nahi aayega.
#
# Safe hai — dobara bhi chala sakte hain, kabhi bhi (idempotent).

from django.core.management.base import BaseCommand
from django.db import transaction
from pos.models.stock_return import StockReturn, ReturnSequence


class Command(BaseCommand):
    help = "Seed ReturnSequence counters from existing live StockReturn data (run once after migration)."

    def handle(self, *args, **options):
        fy_max_numbers = {}  # { "26-27": 15, "25-26": 240, ... }

        returns = StockReturn.objects.exclude(return_no__isnull=True).exclude(return_no="")

        for r in returns.iterator():
            parts = r.return_no.split('/')
            # Expected shapes:
            #   RTN/26-27/0003        -> ['RTN', '26-27', '0003']
            #   RTN/UGF/26-27/0001    -> ['RTN', 'UGF', '26-27', '0001']
            if len(parts) < 3:
                self.stdout.write(self.style.WARNING(
                    f"Skipping unrecognized return_no format: {r.return_no}"
                ))
                continue

            fy = parts[-2]
            number_str = parts[-1]

            try:
                number = int(number_str)
            except ValueError:
                self.stdout.write(self.style.WARNING(
                    f"Skipping non-numeric serial in return_no: {r.return_no}"
                ))
                continue

            if fy not in fy_max_numbers or number > fy_max_numbers[fy]:
                fy_max_numbers[fy] = number

        if not fy_max_numbers:
            self.stdout.write(self.style.SUCCESS(
                "No existing returns found. Nothing to seed — counters will start fresh at 0001."
            ))
            return

        with transaction.atomic():
            for fy, max_number in fy_max_numbers.items():
                seq, created = ReturnSequence.objects.select_for_update().get_or_create(
                    financial_year=fy,
                    defaults={'last_number': max_number},
                )
                if not created and seq.last_number < max_number:
                    seq.last_number = max_number
                    seq.save(update_fields=['last_number'])

                action = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(
                    f"{action} ReturnSequence for FY {fy} → last_number = {max_number}"
                ))

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Done. Next return in each FY will continue correctly from the seeded number."
        ))