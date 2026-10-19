# ecommerce/models/refund.py
import uuid
from django.db import models
from django.utils import timezone
from ecommerce.models.order import Order, OrderItem
from ecommerce.models.return_request import ReturnRequest
from users.models import User


class OrderRefund(models.Model):
    """
    One row per accepted return request.
      - refund_type='online' : Razorpay refund (admin clicks "Process Refund")
      - refund_type='cod'    : manual bank/UPI refund by superadmin, recorded via
                               CODRefundPayment (see below)
    Created automatically when a return becomes vendor_approved / admin_approved
    — see ecommerce/utils/refund_helpers.py.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
    ]

    TYPE_CHOICES = [
        ('online', 'Online (Razorpay)'),
        ('cod', 'COD (Manual Bank Refund)'),
    ]

    refund_id = models.CharField(max_length=50, unique=True, editable=False)

    return_request = models.OneToOneField(
        ReturnRequest, on_delete=models.CASCADE, related_name='refund'
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='refunds')
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='refunds')

    refund_type = models.CharField(
        max_length=10, choices=TYPE_CHOICES, default='online', db_index=True
    )

    # Entitled amount (proportional to returned qty). MLM reversal uses this.
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    # Actual amount sent (COD manual payout). Null for online.
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    razorpay_refund_id = models.CharField(max_length=255, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)

    commission_reversed = models.BooleanField(default=False)

    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.refund_id:
            self.refund_id = f"RFD{timezone.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.refund_id} - {self.order.order_number} ({self.status})"


class ReturnBankDetail(models.Model):
    """
    Customer's bank details for a COD return (money is sent here by superadmin).
    Required only when order.payment_method == 'cod'.
    """
    ACCOUNT_TYPES = [('savings', 'Savings'), ('current', 'Current')]

    return_request = models.OneToOneField(
        ReturnRequest, on_delete=models.CASCADE, related_name='bank_detail'
    )
    account_holder_name = models.CharField(max_length=100)
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    ifsc_code = models.CharField(max_length=11)
    account_type = models.CharField(max_length=10, choices=ACCOUNT_TYPES, default='savings')
    upi_id = models.CharField(max_length=100, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def masked_account_number(self):
        n = self.account_number or ''
        return ('X' * max(0, len(n) - 4)) + n[-4:]

    def __str__(self):
        return f"Bank detail for {self.return_request.return_id}"


class RefundBankAccount(models.Model):
    """
    SUPERADMIN's own bank accounts used to pay COD refunds to customers.
    Completely separate from POS Account / branch — has its own ledger
    (see AdminRefundBankLedgerAPIView).
    """
    account_name = models.CharField(max_length=100)          # display label
    bank_name = models.CharField(max_length=100)
    account_holder_name = models.CharField(max_length=150, blank=True, default='')
    account_number = models.CharField(max_length=20, unique=True)
    ifsc_code = models.CharField(max_length=11)
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='refund_bank_accounts_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.account_name} ({self.bank_name})"


class CODRefundPayment(models.Model):
    """
    One row per COD refund actually paid by superadmin. This is the ledger
    entry (money OUT / credit) of `bank_account`.
    """
    PAYMENT_MODES = [
        ('neft', 'NEFT'),
        ('imps', 'IMPS'),
        ('rtgs', 'RTGS'),
        ('upi', 'UPI'),
        ('net_banking', 'Net Banking'),
        ('cheque', 'Cheque'),
    ]

    voucher_no = models.CharField(max_length=50, unique=True, editable=False)
    refund = models.OneToOneField(
        OrderRefund, on_delete=models.CASCADE, related_name='cod_payment'
    )
    bank_account = models.ForeignKey(
        RefundBankAccount, on_delete=models.PROTECT, related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES)
    reference_no = models.CharField(max_length=100, blank=True, default='')   # UTR / cheque no.
    proof = models.FileField(upload_to='cod_refund_proofs/%Y/%m/')
    narration = models.TextField(blank=True, default='')

    paid_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cod_refunds_paid'
    )
    paid_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_at', '-id']

    def save(self, *args, **kwargs):
        if not self.voucher_no:
            self.voucher_no = f"CRP{timezone.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.voucher_no} - ₹{self.amount}"