# pos/management/commands/fix_return_sequence.py
# NEW FILE
#
# Yeh command 2 kaam karta hai:
#
# 1. DIAGNOSE (default, safe, kuch bhi change nahi karta):
#       python manage.py fix_return_sequence
#    Har FY ke saare returns created_at ke order mein dikhata hai aur
#    batata hai kahin serial number "out of sequence" (jaise ek naya
#    return purane se chhota number le baitha) toh nahi hai.
#
# 2. APPLY (asli fix — return_no renumber karta hai + counter seed karta hai):
#       python manage.py fix_return_sequence --apply
#    ⚠️ Yeh har return ka `return_no` sirf serial part change karega
#    (prefix aur branch_code jaisa tha waisa hi rahega), created_at ke
#    chronological order ke hisaab se 0001, 0002, 0003... sequentially
#    re-assign karega per financial year. Fir ReturnSequence counter ko
#    bhi sahi max pe set kar dega.
#
#    ⚠️ IMPORTANT: Agar aapne kisi return_no ka print-out branch ko bheja
#    hai ya kahin reference use ho raha hai (invoice, WhatsApp message,
#    etc), uska number badal sakta hai. Pehle bina --apply ke chala ke
#    dekh lo ki kaunsa record badalne wala hai.

from django.core.management.base import BaseCommand
from django.db import transaction
from pos.models.stock_return import StockReturn, ReturnSequence


class Command(BaseCommand):
    help = "Diagnose and optionally fix out-of-sequence StockReturn.return_no values."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually renumber return_no values and reseed the counter. Without this flag, only a dry-run report is shown.',
        )

    def parse_return_no(self, return_no):
        """
        Returns (prefix, branch_code_or_None, fy, serial_int) or None if unparseable.
        """
        parts = return_no.split('/')
        if len(parts) == 3:
            prefix, fy, serial_str = parts
            branch_code = None
        elif len(parts) == 4:
            prefix, branch_code, fy, serial_str = parts
        else:
            return None
        try:
            serial = int(serial_str)
        except ValueError:
            return None
        return prefix, branch_code, fy, serial

    def handle(self, *args, **options):
        apply_changes = options['apply']

        returns = list(
            StockReturn.objects.exclude(return_no__isnull=True)
            .exclude(return_no="")
            .order_by('created_at', 'id')  # chronological creation order
        )

        # Group by financial year, preserving chronological order
        fy_groups = {}
        unparseable = []

        for r in returns:
            parsed = self.parse_return_no(r.return_no)
            if not parsed:
                unparseable.append(r)
                continue
            prefix, branch_code, fy, serial = parsed
            fy_groups.setdefault(fy, []).append({
                'obj': r,
                'prefix': prefix,
                'branch_code': branch_code,
                'old_serial': serial,
            })

        if unparseable:
            self.stdout.write(self.style.WARNING(
                f"\n⚠️ {len(unparseable)} return(s) have unrecognized return_no format, skipped:"
            ))
            for r in unparseable:
                self.stdout.write(f"   - id={r.id} return_no={r.return_no!r}")

        any_mismatch = False

        for fy, entries in fy_groups.items():
            self.stdout.write(self.style.HTTP_INFO(f"\n📅 Financial Year {fy} — {len(entries)} return(s)"))
            for expected_serial, entry in enumerate(entries, start=1):
                old_serial = entry['old_serial']
                status = "✅ OK" if old_serial == expected_serial else "❌ MISMATCH"
                if old_serial != expected_serial:
                    any_mismatch = True
                self.stdout.write(
                    f"   {status}  id={entry['obj'].id:>5}  "
                    f"created={entry['obj'].created_at.strftime('%Y-%m-%d %H:%M')}  "
                    f"current={entry['obj'].return_no:<28}  expected_serial={str(expected_serial).zfill(4)}"
                )

        if not any_mismatch:
            self.stdout.write(self.style.SUCCESS("\n✅ Everything is already in correct order. Nothing to fix."))
            # Still make sure the sequence counter is correctly seeded
            if apply_changes:
                self._reseed_counters(fy_groups)
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "\n⚠️ Mismatches found above. This was a DRY RUN — nothing was changed.\n"
                "Re-run with --apply to actually fix the return_no values:\n\n"
                "    python manage.py fix_return_sequence --apply\n"
            ))
            return

        # ── Apply fix ──
        with transaction.atomic():
            for fy, entries in fy_groups.items():
                for expected_serial, entry in enumerate(entries, start=1):
                    obj = entry['obj']
                    if entry['old_serial'] == expected_serial:
                        continue  # already correct, skip write

                    prefix = entry['prefix']
                    branch_code = entry['branch_code']
                    new_serial_str = str(expected_serial).zfill(4)

                    if branch_code:
                        new_return_no = f"{prefix}/{branch_code}/{fy}/{new_serial_str}"
                    else:
                        new_return_no = f"{prefix}/{fy}/{new_serial_str}"

                    old_return_no = obj.return_no
                    obj.return_no = new_return_no
                    obj.save(update_fields=['return_no'])

                    self.stdout.write(self.style.SUCCESS(
                        f"   🔧 Fixed id={obj.id}: {old_return_no} → {new_return_no}"
                    ))

            self._reseed_counters(fy_groups)

        self.stdout.write(self.style.SUCCESS("\n✅ Done. All returns renumbered correctly and counter reseeded."))

    def _reseed_counters(self, fy_groups):
        for fy, entries in fy_groups.items():
            max_number = len(entries)  # after fixing, serials are exactly 1..N
            seq, created = ReturnSequence.objects.select_for_update().get_or_create(
                financial_year=fy,
                defaults={'last_number': max_number},
            )
            if not created and seq.last_number != max_number:
                seq.last_number = max_number
                seq.save(update_fields=['last_number'])
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(
                f"   ↳ {action} ReturnSequence for FY {fy} → last_number = {max_number}"
            ))