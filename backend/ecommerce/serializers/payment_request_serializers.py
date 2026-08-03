# ecommerce/serializers/payment_request_serializers.py
from rest_framework import serializers
from ecommerce.models.payment_request import VendorPaymentRequest
from ecommerce.utils.payment_helpers import get_vendor_eligible_online_orders


class PaymentRequestListSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)

    class Meta:
        model = VendorPaymentRequest
        fields = [
            'id', 'payment_request_id', 'vendor_name', 'date_from', 'date_to',
            'total_order_amount', 'online_platform_charge', 'cod_platform_charge',
            'total_platform_charge', 'release_payment_amount',
            'approved_order_amount', 'approved_online_charge', 'approved_amount',
            'status', 'admin_remarks', 'created_at', 'approved_at', 'paid_at',
        ]


class PaymentRequestDetailSerializer(PaymentRequestListSerializer):
    orders_data = serializers.SerializerMethodField()
    approved_order_ids = serializers.SerializerMethodField()

    class Meta(PaymentRequestListSerializer.Meta):
        fields = PaymentRequestListSerializer.Meta.fields + ['orders_data', 'approved_order_ids']

    def get_orders_data(self, obj):
        from ecommerce.utils.payment_helpers import get_order_summaries

        order_ids = list(obj.orders.values_list('id', flat=True))
        approved_ids = set(obj.approved_orders.values_list('id', flat=True))

        summaries = get_order_summaries(obj.vendor, order_ids)
        for s in summaries:
            s['vendor_total'] = float(s['vendor_total'])
            s['platform_charge'] = float(s['platform_charge'])
            # ✅ NEW: per-order approval status
            if obj.status == 'pending':
                s['approval_status'] = 'pending'
            elif s['order_id'] in approved_ids:
                s['approval_status'] = 'approved'
            elif obj.status == 'rejected':
                s['approval_status'] = 'rejected'
            else:
                s['approval_status'] = 'not_approved'  # partial-approval leftover
        return summaries

    def get_approved_order_ids(self, obj):
        return list(obj.approved_orders.values_list('id', flat=True))


class CreatePaymentRequestSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    order_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate(self, data):
        if data['date_from'] > data['date_to']:
            raise serializers.ValidationError("Start date must be before or equal to end date")

        request = self.context['request']
        vendor = request.user.vendor

        eligible_orders = get_vendor_eligible_online_orders(vendor, data['date_from'], data['date_to'])
        eligible_ids = {o['order_id'] for o in eligible_orders}

        invalid = set(data['order_ids']) - eligible_ids
        if invalid:
            raise serializers.ValidationError(
                f"These orders are not eligible for this date range: {sorted(invalid)}"
            )

        data['_eligible_orders'] = eligible_orders
        return data

    def create(self, validated_data):
        from ecommerce.models.order import Order
        from ecommerce.models.payment_request import VendorPaymentRequest, VendorCODRecovery
        from ecommerce.utils.payment_helpers import get_vendor_cod_platform_charge

        request = self.context['request']
        vendor = request.user.vendor
        order_ids = validated_data['order_ids']
        date_from = validated_data['date_from']
        date_to = validated_data['date_to']

        eligible_orders = validated_data['_eligible_orders']
        selected = [o for o in eligible_orders if o['order_id'] in order_ids]

        total_order_amount = sum((o['vendor_total'] for o in selected), start=0)
        online_platform_charge = sum((o['platform_charge'] for o in selected), start=0)

        cod_platform_charge, cod_item_charges = get_vendor_cod_platform_charge(vendor, date_from, date_to)

        total_platform_charge = online_platform_charge + cod_platform_charge
        release_payment_amount = total_order_amount - total_platform_charge

        payment_request = VendorPaymentRequest.objects.create(
            vendor=vendor,
            date_from=date_from,
            date_to=date_to,
            total_order_amount=total_order_amount,
            online_platform_charge=online_platform_charge,
            cod_platform_charge=cod_platform_charge,
            total_platform_charge=total_platform_charge,
            release_payment_amount=release_payment_amount,
        )
        payment_request.orders.set(Order.objects.filter(id__in=order_ids))

        for item, charge in cod_item_charges:
            VendorCODRecovery.objects.create(
                payment_request=payment_request,
                order_item=item,
                platform_charge_amount=charge,
            )

        return payment_request


class ApprovePaymentRequestSerializer(serializers.Serializer):
    approved_order_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    remarks = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        payment_request = self.context['payment_request']
        if payment_request.status != 'pending':
            raise serializers.ValidationError("Only pending requests can be approved")

        requested_ids = set(payment_request.orders.values_list('id', flat=True))
        approved_ids = data.get('approved_order_ids')

        if approved_ids:
            invalid = set(approved_ids) - requested_ids
            if invalid:
                raise serializers.ValidationError(
                    f"Orders {sorted(invalid)} are not part of this payment request"
                )
        else:
            approved_ids = list(requested_ids)

        data['approved_order_ids'] = approved_ids
        return data