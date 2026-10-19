# ecommerce/serializers/return_serializers.py
import re
from django.db import transaction
from rest_framework import serializers

from ecommerce.models.return_request import ReturnRequest, ReturnRequestImage
from ecommerce.models.order import OrderItem
from ecommerce.models.refund import ReturnBankDetail, OrderRefund
from ecommerce.utils.return_helpers import is_order_item_returnable
from django.core.exceptions import ObjectDoesNotExist

MAX_IMAGES = 5
MAX_IMAGE_SIZE_MB = 2

IFSC_RE = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
ACCOUNT_RE = re.compile(r'^\d{9,18}$')
UPI_RE = re.compile(r'^[a-zA-Z0-9.\-_]{2,60}@[a-zA-Z]{2,30}$')
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{2,99}$")


def _s(data, key):
    v = data.get(key)
    return '' if v is None else str(v).strip()


def validate_bank_details_payload(data):
    """
    Validates the customer's COD refund bank details (flat keys, same names are used
    by the return-create multipart form AND the bank-details update endpoint):
      bank_account_holder, bank_name, bank_account_number,
      bank_confirm_account_number, bank_ifsc, bank_account_type, bank_upi_id
    Returns cleaned dict keyed by ReturnBankDetail model fields, or raises
    serializers.ValidationError({field: message}).
    """
    errors = {}

    holder = _s(data, 'bank_account_holder')
    bank_name = _s(data, 'bank_name')
    number = re.sub(r'\s+', '', _s(data, 'bank_account_number'))
    confirm = re.sub(r'\s+', '', _s(data, 'bank_confirm_account_number'))
    ifsc = _s(data, 'bank_ifsc').upper()
    account_type = (_s(data, 'bank_account_type') or 'savings').lower()
    upi = _s(data, 'bank_upi_id')

    if not holder:
        errors['bank_account_holder'] = "Account holder name is required for COD refunds."
    elif not NAME_RE.match(holder):
        errors['bank_account_holder'] = "Enter a valid account holder name."

    if not bank_name:
        errors['bank_name'] = "Bank name is required for COD refunds."
    elif len(bank_name) < 2 or len(bank_name) > 100:
        errors['bank_name'] = "Enter a valid bank name."

    if not number:
        errors['bank_account_number'] = "Account number is required for COD refunds."
    elif not ACCOUNT_RE.match(number):
        errors['bank_account_number'] = "Account number must be 9 to 18 digits."

    if not confirm:
        errors['bank_confirm_account_number'] = "Please confirm the account number."
    elif number and confirm != number:
        errors['bank_confirm_account_number'] = "Account numbers do not match."

    if not ifsc:
        errors['bank_ifsc'] = "IFSC code is required for COD refunds."
    elif not IFSC_RE.match(ifsc):
        errors['bank_ifsc'] = "Invalid IFSC code (example: SBIN0001234)."

    if account_type not in ('savings', 'current'):
        errors['bank_account_type'] = "Account type must be savings or current."

    if upi and not UPI_RE.match(upi):
        errors['bank_upi_id'] = "Invalid UPI ID (example: name@bank)."

    if errors:
        raise serializers.ValidationError(errors)

    return {
        'account_holder_name': holder,
        'bank_name': bank_name,
        'account_number': number,
        'ifsc_code': ifsc,
        'account_type': account_type,
        'upi_id': upi,
    }


class ReturnRequestListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    product_name = serializers.CharField(source='order_item.product_name', read_only=True)
    sku = serializers.CharField(source='order_item.sku', read_only=True)
    customer_name = serializers.CharField(source='customer.username', read_only=True)
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    payment_method = serializers.CharField(source='order.payment_method', read_only=True)
    item_total = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    has_bank_details = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()

    class Meta:
        model = ReturnRequest
        fields = [
            'id', 'return_id', 'order', 'order_item', 'order_number',
            'product_name', 'sku', 'customer_name', 'vendor_name', 'item_total',
            'reason', 'description', 'images', 'quantity',
            'status', 'vendor_remarks', 'admin_remarks',
            'requested_at', 'vendor_responded_at', 're_requested_at', 'admin_responded_at',
            'payment_method', 'has_bank_details', 'refund_status',
        ]

    def get_item_total(self, obj):
        from ecommerce.utils.refund_helpers import calculate_refund_amount
        return calculate_refund_amount(obj.order_item, obj.quantity)

    def get_images(self, obj):
        request = self.context.get('request')
        urls = []
        for img in obj.return_images.all():
            url = img.image.url
            if request:
                url = request.build_absolute_uri(url)
            urls.append(url)
        return urls

    def get_has_bank_details(self, obj):
        return hasattr(obj, 'bank_detail')

    def get_refund_status(self, obj):
        try:
            return obj.refund.status
        except ObjectDoesNotExist:
            return None


class CreateReturnRequestSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=ReturnRequest.REASON_CHOICES)
    description = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    images = serializers.ListField(
        child=serializers.ImageField(), required=False, default=list
    )

    # ── COD-only bank details (required when order.payment_method == 'cod') ──
    bank_account_holder = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_account_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_confirm_account_number = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_ifsc = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_account_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    bank_upi_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_images(self, value):
        if len(value) > MAX_IMAGES:
            raise serializers.ValidationError(f"You can upload a maximum of {MAX_IMAGES} images")
        for img in value:
            if img.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
                raise serializers.ValidationError(
                    f"'{img.name}' is {round(img.size / (1024*1024), 2)}MB — each image must be under {MAX_IMAGE_SIZE_MB}MB"
                )
        return value

    def validate(self, data):
        request = self.context['request']
        try:
            order_item = OrderItem.objects.select_related('order').get(
                id=data['order_item_id'],
                order__customer=request.user
            )
        except OrderItem.DoesNotExist:
            raise serializers.ValidationError("Order item not found")

        ok, reason = is_order_item_returnable(order_item)
        if not ok:
            raise serializers.ValidationError(reason)

        if data['quantity'] > order_item.quantity:
            raise serializers.ValidationError("Return quantity cannot exceed ordered quantity")

        # COD → customer MUST give bank details (refund is paid manually by superadmin)
        if order_item.order.payment_method == 'cod':
            data['_bank_details'] = validate_bank_details_payload(data)

        data['_order_item'] = order_item
        return data

    @transaction.atomic
    def create(self, validated_data):
        order_item = validated_data['_order_item']
        request = self.context['request']
        images = validated_data.pop('images', [])
        bank_details = validated_data.get('_bank_details')

        return_req = ReturnRequest.objects.create(
            order=order_item.order,
            order_item=order_item,
            vendor=order_item.vendor,
            customer=request.user,
            reason=validated_data['reason'],
            description=validated_data.get('description', ''),
            quantity=validated_data['quantity'],
        )

        for img in images:
            ReturnRequestImage.objects.create(return_request=return_req, image=img)

        if bank_details:
            ReturnBankDetail.objects.create(return_request=return_req, **bank_details)

        return return_req


class VendorReturnActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    remarks = serializers.CharField(required=False, allow_blank=True)


class AdminReturnActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    remarks = serializers.CharField(required=False, allow_blank=True)