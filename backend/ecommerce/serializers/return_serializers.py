from rest_framework import serializers
from ecommerce.models.return_request import ReturnRequest, ReturnRequestImage
from ecommerce.models.order import OrderItem
from ecommerce.utils.return_helpers import is_order_item_returnable

MAX_IMAGES = 5
MAX_IMAGE_SIZE_MB = 2


class ReturnRequestListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    product_name = serializers.CharField(source='order_item.product_name', read_only=True)
    sku = serializers.CharField(source='order_item.sku', read_only=True)
    customer_name = serializers.CharField(source='customer.username', read_only=True)
    vendor_name = serializers.CharField(source='vendor.business_name', read_only=True)
    item_total = serializers.DecimalField(source='order_item.total_price', max_digits=10, decimal_places=2, read_only=True)
    images = serializers.SerializerMethodField()   # ✅ NEW

    class Meta:
        model = ReturnRequest
        fields = [
            'id', 'return_id', 'order', 'order_item', 'order_number',
            'product_name', 'sku', 'customer_name', 'vendor_name', 'item_total',
            'reason', 'description', 'images', 'quantity',   # 'images' ab method field hai
            'status', 'vendor_remarks', 'admin_remarks',
            'requested_at', 'vendor_responded_at', 're_requested_at', 'admin_responded_at',
        ]

    def get_images(self, obj):
        request = self.context.get('request')
        urls = []
        for img in obj.return_images.all():
            url = img.image.url
            if request:
                url = request.build_absolute_uri(url)
            urls.append(url)
        return urls


class CreateReturnRequestSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=ReturnRequest.REASON_CHOICES)
    description = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1, default=1)
    images = serializers.ListField(
        child=serializers.ImageField(), required=False, default=list
    )

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
            order_item = OrderItem.objects.get(
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

        data['_order_item'] = order_item
        return data

    def create(self, validated_data):
        order_item = validated_data['_order_item']
        request = self.context['request']
        images = validated_data.pop('images', [])

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

        return return_req


class VendorReturnActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    remarks = serializers.CharField(required=False, allow_blank=True)


class AdminReturnActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    remarks = serializers.CharField(required=False, allow_blank=True)