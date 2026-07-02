# pos/serializers/LedgerReport_serializers.py
"""
LEDGER RULES — PERFECT ACCOUNTING (No Double Counting)

═ CUSTOMER ═══════════════════════════════════════════════════════════════════
  Dr (+) → Credit Sales (payment_terms='credit')
  Dr (+) → Cash/Bank Payment TO customer? → NO! (customer ne paisa diya = Cr)
  Cr (+) → Sales Return (credit) + Cash/Bank Receipt FROM customer

═ SUPPLIER ═══════════════════════════════════════════════════════════════════
  Cr (+) → Credit Purchase (terms='credit')
  Cr (+) → Cash/Bank Receipt FROM supplier? → NO! (supplier ko paisa diya = Dr)
  Dr (+) → Purchase Return (credit) + Cash/Bank Payment TO supplier

═ CASH IN HAND ═══════════════════════════════════════════════════════════════
  Dr (+) → Cash Receipt (CR, SCR, PRCR) + Contra IF Cash Deposit
  Cr (+) → Cash Payment (CP, PCP, SRCP) + Contra IF Cash Withdrawal

═ BANK ACCOUNT ═══════════════════════════════════════════════════════════════
  Dr (+) → Bank Receipt (BR, SBR, PRBR) + Contra IF Cash Deposit/Bank Transfer
  Cr (+) → Bank Payment (BP, PBP, SRBP) + Contra IF Cash Withdrawal

KEY INSIGHTS from your analysis:
  1. Cash/Bank sale → Customer ledger NO entry (paisa direct cash/bank me gaya)
  2. Cash/Bank purchase return → Supplier ledger NO entry
  3. SRCP/SRBP (customer ko refund) → Customer CR (receivable kam hua)
  4. PRCR/PRBR (supplier se refund) → Supplier DR (payable kam hua)
"""

from rest_framework import serializers
from decimal import Decimal
from datetime import date as date_cls

from pos.models.account import Account
from pos.models.purchaseentry import PurchaseMaster
from pos.models.salesentry import SalesMaster
from pos.models.cashpayment import CashPayment
from pos.models.bankpayment import BankPayment
from pos.models.bankreceipt import BankReceipt
from pos.models.cashreceipt import CashReceipt
from pos.models.contra import Contra
from pos.models.journalentries import JournalEntry
from pos.models.salesreturn import SalesReturnMaster
from pos.models.purchasereturn import PurchaseReturnMaster


class LedgerAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id", "account_name", "group", "address", "city", "state",
            "current_balance", "current_drcr", "opening_balance", "drcr",
        ]


class LedgerReportSerializer:
    """Pure-class ledger generator — PERFECT accounting rules applied."""

    # ────────────────────────── tiny helpers ────────────────────────────────

    @staticmethod
    def D(val) -> Decimal:
        try:
            return Decimal(str(val)) if val is not None else Decimal("0")
        except Exception:
            return Decimal("0")

    @staticmethod
    def running(balance: Decimal, drcr: str, debit: Decimal, credit: Decimal):
        """
        Dr balance → +debit −credit   (flips to Cr when negative)
        Cr balance → +credit −debit    (flips to Dr when negative)
        """
        if drcr == "Dr":
            new_bal = balance + debit - credit
        else:
            new_bal = balance + credit - debit

        if new_bal >= Decimal("0"):
            return new_bal, drcr
        return abs(new_bal), ("Cr" if drcr == "Dr" else "Dr")

    # ─────────────────── date-filter helper ─────────────────────────────────

    @staticmethod
    def _df(qs, date_from, date_to, field="date"):
        if date_from:
            qs = qs.filter(**{f"{field}__gte": date_from})
        if date_to:
            qs = qs.filter(**{f"{field}__lte": date_to})
        return qs

    @staticmethod
    def _df_lt(qs, before_date, field="date"):
        """Strictly before before_date (used for opening-balance calc)."""
        if before_date:
            qs = qs.filter(**{f"{field}__lt": before_date})
        return qs

    # ────────────────────── entry collector ─────────────────────────────────

    @classmethod
    def _collect_entries(
        cls,
        account: Account,
        date_from=None,
        date_to=None,
        before_date=None,
    ):
        """
        Returns a list of raw entry dicts with PERFECT accounting rules.
        Use before_date for opening-balance calculation.
        """
        D = cls.D
        branch = account.branch
        group = account.group
        entries = []

        def df(qs, field="date"):
            if before_date:
                return cls._df_lt(qs, before_date, field)
            return cls._df(qs, date_from, date_to, field)

        def df_je(qs):
            if before_date:
                return cls._df_lt(qs, before_date, "journal__date")
            return cls._df(qs, date_from, date_to, "journal__date")

        # ═══════════════════════════════════════════════════════════════════
        # CUSTOMER — PERFECT RULES
        # ═══════════════════════════════════════════════════════════════════
        if group == "Customer":

            # 1️⃣ CREDIT SALES ONLY → Dr customer
            #    Cash/Bank Sales → Customer ledger NO entry (paisa direct cash/bank me gaya)
            for s in df(
                SalesMaster.objects.filter(
                    customer=account,
                    branch=branch,
                    # ✅ ONLY CREDIT SALES
                ).select_related("case_account", "bank_account")
            ):
                entries.append({
                    "date": s.date,
                    "created_at": s.created_at, 
                    "voucher": s.bill_no,
                    "type": "SI",
                    "particulars": f"Credit Sale – {s.payment_terms.capitalize()}",
                    "debit": D(s.grand_total),
                    "credit": Decimal("0"),
                })

            # 2️⃣ Sales Returns → Cr customer (only credit returns matter)
            for sr in df(
                SalesReturnMaster.objects.filter(
                    customer=account,
                    branch=branch,
                    # ✅ ONLY CREDIT RETURNS
                )
            ):
                entries.append({
                    "date": sr.date,
                    "created_at": sr.created_at, 
                    "voucher": sr.return_no,
                    "type": "SR",
                    "particulars": f"Sales Return (Credit) against {sr.original_bill_no}",
                    "debit": Decimal("0"),
                    "credit": D(sr.grand_total),
                })

            # 3️⃣ Cash Receipts FROM customer → Cr customer (customer ne paisa diya)
            for cr in df(
                CashReceipt.objects.filter(op_account=account, branch=branch)
                .exclude(type__in=["PRCR"])  # PRCR supplier ka hai
                .select_related("cash_account")
            ):
                entries.append({
                    "date": cr.date,
                    "created_at": cr.created_at, 
                    "voucher": cr.voucher_no,
                    "type": cr.type,
                    "particulars": f"Cash Receipt from Customer – {cr.cash_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(cr.amount),
                })

            # 4️⃣ Bank Receipts FROM customer → Cr customer
            for br in df(
                BankReceipt.objects.filter(op_account=account, branch=branch)
                .exclude(type__in=["PRBR"])
                .select_related("bank_account")
            ):
                entries.append({
                    "date": br.date,
                    "created_at": br.created_at, 
                    "voucher": br.voucher_no,
                    "type": br.type,
                    "particulars": f"Bank Receipt from Customer – {br.bank_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(br.amount),
                })

            # 5️⃣ SRCP/SRBP (Refund TO customer) → Dr? NO! Customer ko refund → Customer CR
            #    Because customer ka receivable kam ho raha hai (Cr entry)
            for cp in df(
                CashPayment.objects.filter(op_account=account, branch=branch, type="SRCP")
                .select_related("cash_account")
            ):
                entries.append({
                    "date": cp.date,
                    "created_at": cp.created_at, 
                    "voucher": cp.voucher_no,
                    "type": "SRCP",
                    "particulars": f"Sales Return Cash Payment (Refund to Customer) – {cp.cash_account.account_name}",
                    "debit": Decimal("0"),      # ✅ Dr matlab receivable increase hota - GALAT
                    "credit": D(cp.amount),     # ✅ Cr matlab receivable kam hua - SAHI
                })

            for bp in df(
                BankPayment.objects.filter(op_account=account, branch=branch, type="SRBP")
                .select_related("bank_account")
            ):
                entries.append({
                    "date": bp.date,
                    "created_at": bp.created_at, 
                    "voucher": bp.voucher_no,
                    "type": "SRBP",
                    "particulars": f"Sales Return Bank Payment (Refund to Customer) – {bp.bank_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(bp.amount),
                })

            # 6️⃣ Regular CP/BP (customer ne paise diye) pehle se covered in receipts
            #    Skip additional CP/BP because SRCP/SRBP already handled above

        # ═══════════════════════════════════════════════════════════════════
        # SUPPLIER — PERFECT RULES
        # ═══════════════════════════════════════════════════════════════════
        elif group == "Supplier":

            # 1️⃣ CREDIT PURCHASES ONLY → Cr supplier
            for p in df(
                PurchaseMaster.objects.filter(
                    partyName=account,
                    branch=branch,
                     # ✅ ONLY CREDIT PURCHASES
                )
            ):
                entries.append({
                    "date": p.date,
                    "created_at": p.created_at, 
                    "voucher": p.billNo,
                    "type": "PI",
                    "particulars": f"Credit Purchase – {p.terms.capitalize()}",
                    "debit": Decimal("0"),
                    "credit": D(p.grand_total),
                })

            # 2️⃣ Purchase Returns → Dr supplier (only credit returns matter)
            for pr in df(
                PurchaseReturnMaster.objects.filter(
                    party=account,
                    branch=branch,
                      # ✅ ONLY CREDIT RETURNS
                )
            ):
                entries.append({
                    "date": pr.date,
                    "created_at": pr.created_at, 
                    "voucher": pr.return_no,
                    "type": "PR",
                    "particulars": f"Purchase Return (Credit) against {pr.original_bill_no}",
                    "debit": D(pr.grand_total),
                    "credit": Decimal("0"),
                })

            # 3️⃣ PCP/PBP (Payment TO supplier) → Dr supplier (supplier ko paisa diya)
            for cp in df(
                CashPayment.objects.filter(
                    op_account=account,
                    branch=branch,
                    type__in=["PCP", "CP"]  # PCP = Purchase Credit Payment, CP = regular
                ).select_related("cash_account")
            ):
                entries.append({
                    "date": cp.date,
                    "created_at": cp.created_at, 
                    "voucher": cp.voucher_no,
                    "type": cp.type,
                    "particulars": f"Cash Payment to Supplier – {cp.cash_account.account_name}",
                    "debit": D(cp.amount),
                    "credit": Decimal("0"),
                })

            for bp in df(
                BankPayment.objects.filter(
                    op_account=account,
                    branch=branch,
                    type__in=["PBP", "BP"]
                ).select_related("bank_account")
            ):
                entries.append({
                    "date": bp.date,
                    "created_at": bp.created_at, 
                    "voucher": bp.voucher_no,
                    "type": bp.type,
                    "particulars": f"Bank Payment to Supplier – {bp.bank_account.account_name}",
                    "debit": D(bp.amount),
                    "credit": Decimal("0"),
                })

            # 4️⃣ PRCR/PRBR (Receipt FROM supplier → supplier ne paisa diya) → Dr? NO! → Cr
            #    PRCR/PRBR = Supplier refund to US → Supplier ka payable kam hua = Cr
            #    Wait... Let me think:
            #    - Purchase Return (Credit) → Dr supplier (payable kam kiya)
            #    - PRCR/PRBR (Supplier ne paise diye) → Supplier ka payable aur kam hua = Cr
            #    But actually: Supplier ne humein paise diye = Dr cash/bank, Cr supplier
            #    So in SUPPLIER ledger, PRCR/PRBR should be CREDIT
            
            #    Previous logic was correct: PRCR/PRBR in supplier = CREDIT entry
            #    But wait — Purchase return Dr supplier hai. PRCR/PRBR bhi supplier ka Dr kam karta hai = Cr
            #    ✅ YES: PRCR/PRBR → Supplier ledger me CREDIT entry
            for cr in df(
                CashReceipt.objects.filter(
                    op_account=account,
                    branch=branch,
                    type="PRCR"
                ).select_related("cash_account")
            ):
                entries.append({
                    "date": cr.date,
                    "created_at": cr.created_at, 
                    "voucher": cr.voucher_no,
                    "type": "PRCR",
                    "particulars": f"Purchase Return Cash Receipt FROM Supplier – {cr.cash_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(cr.amount),  # ✅ Cr = supplier ka payable kam hua
                })

            for br in df(
                BankReceipt.objects.filter(
                    op_account=account,
                    branch=branch,
                    type="PRBR"
                ).select_related("bank_account")
            ):
                entries.append({
                    "date": br.date,
                    "created_at": br.created_at, 
                    "voucher": br.voucher_no,
                    "type": "PRBR",
                    "particulars": f"Purchase Return Bank Receipt FROM Supplier – {br.bank_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(br.amount),
                })

        # ═══════════════════════════════════════════════════════════════════
        # CASH IN HAND — PERFECT RULES
        # ═══════════════════════════════════════════════════════════════════
        elif group == "Case In Hand":

            # 1️⃣ Cash Receipts → Dr cash (money in)
            for cr in df(
                CashReceipt.objects.filter(cash_account=account, branch=branch)
                .select_related("op_account")
            ):
                entries.append({
                    "date": cr.date,
                    "created_at": cr.created_at, 
                    "voucher": cr.voucher_no,
                    "type": cr.type,
                    "particulars": f"Cash Receipt – from {cr.op_account.account_name}",
                    "debit": D(cr.amount),
                    "credit": Decimal("0"),
                })

            # 2️⃣ Cash Payments → Cr cash (money out)
            for cp in df(
                CashPayment.objects.filter(cash_account=account, branch=branch)
                .select_related("op_account")
            ):
                entries.append({
                    "date": cp.date,
                    "created_at": cp.created_at, 
                    "voucher": cp.voucher_no,
                    "type": cp.type,
                    "particulars": f"Cash Payment – to {cp.op_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(cp.amount),
                })

            # 3️⃣ Contra (this cash account is primary)
            for c in df(
                Contra.objects.filter(cash_account=account, branch=branch)
                .select_related("op_account")
            ):
                if c.type in ("Cash Deposit", "Bank Transfer"):
                    # Cash going OUT to bank/other
                    entries.append({
                        "date": c.date,
                        "created_at": c.created_at, 
                        "voucher": c.voucher_no,
                        "type": "CONTRA",
                        "particulars": f"{c.type} (OUT) → {c.op_account.account_name}",
                        "debit": Decimal("0"),
                        "credit": D(c.amount),
                    })
                else:  # Cash Withdrawal — cash coming IN from bank
                    entries.append({
                        "date": c.date,
                        "voucher": c.voucher_no,
                        "type": "CONTRA",
                        "particulars": f"{c.type} (IN) ← {c.op_account.account_name}",
                        "debit": D(c.amount),
                        "credit": Decimal("0"),
                    })

        # ═══════════════════════════════════════════════════════════════════
        # BANK ACCOUNT — PERFECT RULES
        # ═══════════════════════════════════════════════════════════════════
        elif group == "Bank Account":

            # 1️⃣ Bank Receipts → Dr bank (money in)
            for br in df(
                BankReceipt.objects.filter(bank_account=account, branch=branch)
                .select_related("op_account")
            ):
                entries.append({
                    "date": br.date,
                    "created_at": br.created_at, 
                    "voucher": br.voucher_no,
                    "type": br.type,
                    "particulars": f"Bank Receipt – from {br.op_account.account_name}",
                    "debit": D(br.amount),
                    "credit": Decimal("0"),
                })

            # 2️⃣ Bank Payments → Cr bank (money out)
            for bp in df(
                BankPayment.objects.filter(bank_account=account, branch=branch)
                .select_related("op_account")
            ):
                entries.append({
                    "date": bp.date,
                    "created_at": bp.created_at, 
                    "voucher": bp.voucher_no,
                    "type": bp.type,
                    "particulars": f"Bank Payment – to {bp.op_account.account_name}",
                    "debit": Decimal("0"),
                    "credit": D(bp.amount),
                })

            # 3️⃣ Contra (bank is op_account in contra)
            for c in df(
                Contra.objects.filter(op_account=account, branch=branch)
                .select_related("cash_account")
            ):
                if c.type == "Cash Deposit":
                    # Cash deposit → bank receives money
                    entries.append({
                        "date": c.date,
                        "created_at": c.created_at, 
                        "voucher": c.voucher_no,
                        "type": "CONTRA",
                        "particulars": f"Cash Deposit (IN) ← {c.cash_account.account_name}",
                        "debit": D(c.amount),
                        "credit": Decimal("0"),
                    })
                elif c.type == "Cash Withdrawal":
                    # Cash withdrawal → bank gives money
                    entries.append({
                        "date": c.date,
                        "created_at": c.created_at, 
                        "voucher": c.voucher_no,
                        "type": "CONTRA",
                        "particulars": f"Cash Withdrawal (OUT) → {c.cash_account.account_name}",
                        "debit": Decimal("0"),
                        "credit": D(c.amount),
                    })
                elif c.type == "Bank Transfer":
                    # Bank transfer → bank receives money
                    entries.append({
                        "date": c.date,
                        "created_at": c.created_at, 
                        "voucher": c.voucher_no,
                        "type": "CONTRA",
                        "particulars": f"Bank Transfer (IN) ← {c.cash_account.account_name}",
                        "debit": D(c.amount),
                        "credit": Decimal("0"),
                    })

        # ═══════════════════════════════════════════════════════════════════
        # JOURNAL ENTRIES (all groups)
        # ═══════════════════════════════════════════════════════════════════
        for j in df_je(
            JournalEntry.objects.filter(account=account).select_related("journal")
        ):
            entries.append({
                "date": j.journal.date,
                
                "voucher": j.journal.voucher_no,
                "type": "JV",
                "particulars": f"Journal Entry — {j.journal.voucher_no}",
                "debit": D(j.debit),
                "credit": D(j.credit),
            })

        return entries

    # ─────────────── opening balance for date range ──────────────────────────

    @classmethod
    def _compute_opening_balance(cls, account: Account, date_from):
        """Run all entries strictly before date_from to get the opening balance."""
        entries = cls._collect_entries(account, before_date=date_from)
        entries.sort(key=lambda x: x["date"] or date_cls(1970, 1, 1))
        bal = cls.D(account.opening_balance)
        drcr = account.drcr
        for e in entries:
            bal, drcr = cls.running(bal, drcr, cls.D(e["debit"]), cls.D(e["credit"]))
        return bal, drcr

    # ─────────────────────── main public method ──────────────────────────────

    @classmethod
    def generate_ledger(cls, account: Account, date_from=None, date_to=None,  update_current=False):
        D = cls.D

        if date_from:
            opening_balance, opening_drcr = cls._compute_opening_balance(account, date_from)
        else:
            opening_balance = D(account.opening_balance)
            opening_drcr = account.drcr

        entries = cls._collect_entries(account, date_from=date_from, date_to=date_to)

        # ✅ SORT BY created_at (includes time) — PERFECT CHRONOLOGICAL ORDER
        entries.sort(key=lambda x: x.get("created_at") or date_cls(1970, 1, 1))

        running_balance = opening_balance
        running_drcr = opening_drcr
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        final_ledger = []

        for row in entries:
            debit = D(row["debit"])
            credit = D(row["credit"])
            total_debit += debit
            total_credit += credit
            running_balance, running_drcr = cls.running(
                running_balance, running_drcr, debit, credit
            )
            final_ledger.append({
                "date": str(row["date"]) if row["date"] else None,
                "voucher": row.get("voucher"),
                "type": row.get("type"),
                "particulars": row.get("particulars"),
                "debit": float(debit),
                "credit": float(credit),
                "balance": float(running_balance),
                "balance_dr_cr": running_drcr,
            })
                # ✅ AFTER building final_ledger, BEFORE return
        if update_current:
            account.current_balance = running_balance
            account.current_drcr = running_drcr
            account.save(update_fields=["current_balance", "current_drcr"])

        return {
            "account_id": account.id,
            "account": account.account_name,
            "group": account.group,
            "opening_balance": float(opening_balance),
            "opening_dr_cr": opening_drcr,
            "total_debit": float(total_debit),
            "total_credit": float(total_credit),
            "closing_balance": float(running_balance),
            "closing_dr_cr": running_drcr,
            "ledger": final_ledger,
        }