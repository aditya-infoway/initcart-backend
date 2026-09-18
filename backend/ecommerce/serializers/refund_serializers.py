# ecommerce/serializers/refund_serializers.py
from rest_framework import serializers
from ecommerce.models.refund import OrderRefund


class RefundListSerializer(serializers.ModelSerializer):
    return_id = serializers.CharField(source='return_request.return_id', read_only=True)
    return_status = serializers.CharField(source='return_request.status', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    product_name = serializers.CharField(source='order_item.product_name', read_only=True)
    customer_name = serializers.CharField(source='return_request.customer.username', read_only=True)
    vendor_name = serializers.CharField(source='order_item.vendor.business_name', read_only=True)

    class Meta:
        model = OrderRefund
        fields = [
            'id', 'refund_id', 'return_id', 'return_status',
            'order_number', 'product_name', 'customer_name', 'vendor_name',
            'refund_amount', 'status', 'razorpay_refund_id', 'failure_reason',
            'processed_at', 'created_at',
        ]


class ProcessRefundSerializer(serializers.Serializer):
    """
    No required fields today — kept as a real serializer (rather than
    skipping validation) so we can add admin remarks / amount override
    later without breaking the endpoint's shape.
    """
    remarks = serializers.CharField(required=False, allow_blank=True)