# ecommerce/serializers/refund_serializers.py
import os
import re
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum
from rest_framework import serializers

from ecommerce.models.refund import (
    OrderRefund, RefundBankAccount, CODRefundPayment,
)

MAX_PROOF_BYTES = 1 * 1024 * 1024  # 1 MB
ALLOWED_PROOF_EXT = ('.jpg', '.jpeg', '.png', '.pdf')

IFSC_RE = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
ACCOUNT_RE = re.compile(r'^\d{9,18}$')


def file_url(request, f):
    if not f:
        return None
    try:
        url = f.url
    except Exception:
        return None
    return request.build_absolute_uri(url) if request else url


def _cod_payment(obj):
    try:
        return obj.cod_payment
    except ObjectDoesNotExist:
        return None


class RefundListSerializer(serializers.ModelSerializer):
    return_id = serializers.CharField(source='return_request.return_id', read_only=True)
    return_status = serializers.CharField(source='return_request.status', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    product_name = serializers.CharField(source='order_item.product_name', read_only=True)
    customer_name = serializers.CharField(source='return_request.customer.username', read_only=True)
    vendor_name = serializers.CharField(source='order_item.vendor.business_name', read_only=True)

    has_bank_details = serializers.SerializerMethodField()
    voucher_no = serializers.SerializerMethodField()
    bank_account_name = serializers.SerializerMethodField()
    payment_mode = serializers.SerializerMethodField()
    payment_mode_display = serializers.SerializerMethodField()
    payment_proof = serializers.SerializerMethodField()

    class Meta:
        model = OrderRefund
        fields = [
            'id', 'refund_id', 'refund_type', 'return_id', 'return_status',
            'order_number', 'product_name', 'customer_name', 'vendor_name',
            'refund_amount', 'paid_amount', 'status', 'razorpay_refund_id', 'failure_reason',
            'processed_at', 'created_at',
            'has_bank_details', 'voucher_no', 'bank_account_name',
            'payment_mode', 'payment_mode_display', 'payment_proof',
        ]

    def get_has_bank_details(self, obj):
        if obj.refund_type != 'cod':
            return None
        return hasattr(obj.return_request, 'bank_detail')

    def get_voucher_no(self, obj):
        p = _cod_payment(obj)
        return p.voucher_no if p else None

    def get_bank_account_name(self, obj):
        p = _cod_payment(obj)
        return p.bank_account.account_name if p else None

    def get_payment_mode(self, obj):
        p = _cod_payment(obj)
        return p.payment_mode if p else None

    def get_payment_mode_display(self, obj):
        p = _cod_payment(obj)
        return p.get_payment_mode_display() if p else None

    def get_payment_proof(self, obj):
        p = _cod_payment(obj)
        return file_url(self.context.get('request'), p.proof) if p else None


class ProcessRefundSerializer(serializers.Serializer):
    """
    No required fields today — kept as a real serializer so we can add
    admin remarks / amount override later without breaking the endpoint's shape.
    """
    remarks = serializers.CharField(required=False, allow_blank=True)


# ───────────────────────── COD refund detail (admin pay form) ─────────────────────────

class CODRefundDetailSerializer(serializers.ModelSerializer):
    return_info = serializers.SerializerMethodField()
    order_info = serializers.SerializerMethodField()
    customer_info = serializers.SerializerMethodField()
    product_info = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source='order_item.vendor.business_name', read_only=True)
    bank_details = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()

    class Meta:
        model = OrderRefund
        fields = [
            'id', 'refund_id', 'refund_type', 'status', 'refund_amount', 'paid_amount',
            'failure_reason', 'processed_at', 'created_at',
            'return_info', 'order_info', 'customer_info', 'product_info',
            'vendor_name', 'bank_details', 'payment',
        ]

    def get_return_info(self, obj):
        rr = obj.return_request
        return {
            'return_id': rr.return_id,
            'reason': rr.get_reason_display(),
            'description': rr.description,
            'quantity': rr.quantity,
            'status': rr.status,
            'requested_at': rr.requested_at,
        }

    def get_order_info(self, obj):
        o = obj.order
        return {
            'order_number': o.order_number,
            'order_date': o.created_at,
            'payment_method': o.payment_method,
            'final_amount': o.final_amount,
        }

    def get_customer_info(self, obj):
        c = obj.return_request.customer
        o = obj.order
        return {
            'username': c.username,
            'email': c.email,
            'phone': getattr(c, 'phone', '') or o.billing_phone,
            'billing_name': o.billing_name,
        }

    def get_product_info(self, obj):
        it = obj.order_item
        image = None
        request = self.context.get('request')
        try:
            if it.product_stock and it.product_stock.variant_image:
                image = file_url(request, it.product_stock.variant_image)
            elif it.product and it.product.main_image:
                image = file_url(request, it.product.main_image)
        except Exception:
            image = None
        return {
            'product_name': it.product_name,
            'sku': it.sku,
            'color': it.color,
            'size': it.size,
            'ordered_quantity': it.quantity,
            'returned_quantity_requested': obj.return_request.quantity,
            'unit_price': it.unit_price,
            'total_price': it.total_price,
            'image': image,
        }

    def get_bank_details(self, obj):
        try:
            b = obj.return_request.bank_detail
        except ObjectDoesNotExist:
            return None
        return {
            'account_holder_name': b.account_holder_name,
            'bank_name': b.bank_name,
            'account_number': b.account_number,
            'ifsc_code': b.ifsc_code,
            'account_type': b.account_type,
            'upi_id': b.upi_id,
        }

    def get_payment(self, obj):
        p = _cod_payment(obj)
        if not p:
            return None
        return {
            'voucher_no': p.voucher_no,
            'bank_account': p.bank_account.account_name,
            'amount': p.amount,
            'payment_mode': p.payment_mode,
            'payment_mode_display': p.get_payment_mode_display(),
            'reference_no': p.reference_no,
            'narration': p.narration,
            'proof': file_url(self.context.get('request'), p.proof),
            'paid_at': p.paid_at,
        }


# ───────────────────────── Superadmin refund bank accounts ─────────────────────────

class RefundBankAccountSerializer(serializers.ModelSerializer):
    total_paid = serializers.SerializerMethodField()
    closing_balance = serializers.SerializerMethodField()
    payments_count = serializers.SerializerMethodField()

    class Meta:
        model = RefundBankAccount
        fields = [
            'id', 'account_name', 'bank_name', 'account_holder_name',
            'account_number', 'ifsc_code', 'opening_balance', 'is_active',
            'created_at', 'total_paid', 'closing_balance', 'payments_count',
        ]
        read_only_fields = ['created_at']

    def _paid(self, obj):
        v = getattr(obj, '_paid', None)
        if v is None:
            v = obj.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        return Decimal(str(v))

    def get_total_paid(self, obj):
        return float(self._paid(obj))

    def get_closing_balance(self, obj):
        return float(Decimal(str(obj.opening_balance)) - self._paid(obj))

    def get_payments_count(self, obj):
        c = getattr(obj, '_count', None)
        return c if c is not None else obj.payments.count()

    def validate_account_name(self, value):
        value = (value or '').strip()
        if len(value) < 2:
            raise serializers.ValidationError("Enter an account name.")
        return value

    def validate_bank_name(self, value):
        value = (value or '').strip()
        if len(value) < 2:
            raise serializers.ValidationError("Enter a bank name.")
        return value

    def validate_account_number(self, value):
        value = re.sub(r'\s+', '', value or '')
        if not ACCOUNT_RE.match(value):
            raise serializers.ValidationError("Account number must be 9 to 18 digits.")
        qs = RefundBankAccount.objects.filter(account_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
            if value != self.instance.account_number and self.instance.payments.exists():
                raise serializers.ValidationError(
                    "Account number cannot be changed after payments have been made from it."
                )
        if qs.exists():
            raise serializers.ValidationError("This account number is already added.")
        return value

    def validate_ifsc_code(self, value):
        value = (value or '').strip().upper()
        if not IFSC_RE.match(value):
            raise serializers.ValidationError("Invalid IFSC code (example: SBIN0001234).")
        
        return value

    def validate_opening_balance(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError("Opening balance cannot be negative.")
        return value


# ───────────────────────── COD refund payout (submit form) ─────────────────────────

class CODRefundPaySerializer(serializers.Serializer):
    bank_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    payment_mode = serializers.ChoiceField(choices=CODRefundPayment.PAYMENT_MODES)
    reference_no = serializers.CharField(required=False, allow_blank=True, max_length=100)
    narration = serializers.CharField(required=False, allow_blank=True, max_length=500)
    proof = serializers.FileField(allow_empty_file=False)

    def validate_bank_account_id(self, value):
        try:
            acc = RefundBankAccount.objects.get(pk=value)
        except RefundBankAccount.DoesNotExist:
            raise serializers.ValidationError("Selected bank account not found.")
        if not acc.is_active:
            raise serializers.ValidationError("Selected bank account is inactive.")
        self._bank_account = acc
        return value

    def validate_proof(self, f):
        ext = os.path.splitext((f.name or '').lower())[1]
        if ext not in ALLOWED_PROOF_EXT:
            raise serializers.ValidationError("Proof must be a JPG, PNG or PDF file.")
        if f.size > MAX_PROOF_BYTES:
            raise serializers.ValidationError("Proof file must be 1 MB or smaller.")

        head = f.read(8)
        f.seek(0)
        is_pdf = head.startswith(b'%PDF')
        is_png = head.startswith(b'\x89PNG\r\n\x1a\n')
        is_jpg = head.startswith(b'\xff\xd8')
        if (ext == '.pdf' and not is_pdf) or (ext == '.png' and not is_png) \
                or (ext in ('.jpg', '.jpeg') and not is_jpg):
            raise serializers.ValidationError("File content does not match its extension.")
        return f

    def validate(self, attrs):
        refund = self.context['refund']
        amount = attrs['amount']
        entitled = Decimal(str(refund.refund_amount))

        if amount > entitled:
            raise serializers.ValidationError(
                {'amount': f"Amount cannot exceed the refund amount (₹{entitled})."}
            )
        if amount < entitled and not (attrs.get('narration') or '').strip():
            raise serializers.ValidationError(
                {'narration': "Narration is required when paying less than the refund amount."}
            )
        attrs['bank_account'] = self._bank_account
        return attrs



class VendorRefundListSerializer(RefundListSerializer):
    """
    Vendor / branch view of a refund. Admin-only details (superadmin's bank account,
    payment proof, voucher, Razorpay ids, failure reason) are NOT exposed.
    """
    class Meta(RefundListSerializer.Meta):
        fields = [
            'id', 'refund_id', 'refund_type', 'return_id', 'return_status',
            'order_number', 'product_name', 'customer_name',
            'refund_amount', 'paid_amount', 'status',
            'processed_at', 'created_at',
        ]