# ecommerce/serializers/coupon_serializers.py


from xml.dom import ValidationErr
from rest_framework import serializers
from ecommerce.models.coupon import Coupon, CouponUsage
from ecommerce.models.vendor import Vendor
from ecommerce.models.product import Product
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from django.utils import timezone
import uuid
from decimal import Decimal
import traceback


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class SubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ['id', 'name']


class SubSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubSubCategory
        fields = ['id', 'name']


class ProductMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'product_name', 'sku', 'main_image']


class CouponSerializer(serializers.ModelSerializer):

    class Meta:
        model = Coupon
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # 🔥 IDs return karo for update form
        data["categories"] = list(instance.categories.values_list("id", flat=True))
        data["subcategories"] = list(instance.subcategories.values_list("id", flat=True))
        data["subsubcategories"] = list(instance.subsubcategories.values_list("id", flat=True))
        data["products"] = list(instance.products.values_list("id", flat=True))

        return data

    
class CouponWriteSerializer(serializers.ModelSerializer):

    categories = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        many=True,
        required=False
    )

    subcategories = serializers.PrimaryKeyRelatedField(
        queryset=SubCategory.objects.all(),
        many=True,
        required=False
    )

    subsubcategories = serializers.PrimaryKeyRelatedField(
        queryset=SubSubCategory.objects.all(),
        many=True,
        required=False
    )

    products = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        many=True,
        required=False
    )
    class Meta:
        model = Coupon
        exclude = ["vendor"] 
        
    
    def validate(self, data):
        apply_on = data.get('apply_on')

        categories = data.get('categories') or []
        subcategories = data.get('subcategories') or []
        subsubcategories = data.get('subsubcategories') or []
        products = data.get('products') or []

        # ---------- REQUIRED VALIDATION ----------
        if apply_on == 'category' and not (categories or subcategories or subsubcategories):
            raise serializers.ValidationError({
                'categories': 'At least one category / subcategory is required.'
            })

        if apply_on == 'product' and not products:
            raise serializers.ValidationError({
                'products': 'At least one product is required.'
            })

        # ---------- 🔥 CORE FIX ----------
        if apply_on == 'category':
            if subsubcategories:
                data['categories'] = data.get('categories', [])
                data['subcategories'] = data.get('subcategories', [])

            elif subcategories:
                data['categories'] = data.get('categories', [])

        if apply_on == 'product':
            data['categories'] = []
            data['subcategories'] = []
            data['subsubcategories'] = []

        return data
        
    def create(self, validated_data):
        products = validated_data.pop("products", [])
        categories = validated_data.pop("categories", [])
        subcategories = validated_data.pop("subcategories", [])
        subsubcategories = validated_data.pop("subsubcategories", [])

        coupon = Coupon.objects.create(**validated_data)

        coupon.products.set(products)
        coupon.categories.set(categories)
        coupon.subcategories.set(subcategories)
        coupon.subsubcategories.set(subsubcategories)

        coupon.multiple_selections = {
            "multiple_categories": [c.id for c in categories],
            "multiple_subcategories": [sc.id for sc in subcategories],
            "multiple_subsubcategories": [ssc.id for ssc in subsubcategories],
            "multiple_products": [p.id for p in products],
        }


        coupon.save(update_fields=["multiple_selections"])

        return coupon


    def update(self, instance, validated_data):
        request = self.context.get('request')

        # 🔐 Security: vendor sirf apna coupon update kare
        if instance.vendor != request.user.vendor:
            raise serializers.ValidationError("You cannot update this coupon.")

        # M2M fields nikaal lo
        categories = validated_data.pop('categories', [])
        subcategories = validated_data.pop('subcategories', [])
        subsubcategories = validated_data.pop('subsubcategories', [])
        products = validated_data.pop('products', [])

        # 🔄 Normal fields update
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # 🔄 M2M update
        instance.categories.set(categories)
        instance.subcategories.set(subcategories)
        instance.subsubcategories.set(subsubcategories)
        instance.products.set(products)

        # 🧠 JSON field sync
        instance.multiple_selections = {
            "multiple_categories": list(instance.categories.values_list('id', flat=True)),
            "multiple_subcategories": list(instance.subcategories.values_list('id', flat=True)),
            "multiple_subsubcategories": list(instance.subsubcategories.values_list('id', flat=True)),
            "multiple_products": list(instance.products.values_list('id', flat=True)),
        }

        instance.save(update_fields=["multiple_selections", "updated_at"])

        return instance

class CouponReadSerializer(serializers.ModelSerializer):
    categories = serializers.SerializerMethodField()
    subcategories = serializers.SerializerMethodField()
    subsubcategories = serializers.SerializerMethodField()
    products = serializers.SerializerMethodField()

    class Meta:
        model = Coupon
        fields = [
            "id",
            "vendor",
            "code",
            "title",
            "coupon_type", 
            "discount_percent",
            "discount_amount",
            "max_discount",
            "limit_per_user",
            "min_order_value",
            "apply_on",
            "display_message",
            "max_count",
            "used_count",
            "start_date",
            "expire_date",
            "status",
            "categories",
            "subcategories",
            "subsubcategories",
            "products",
            "multiple_selections",
            "created_at",
            "is_valid",
        ]

    def get_categories(self, obj):
        return [{"value": c.id, "label": c.name} for c in obj.categories.all()]

    def get_subcategories(self, obj):
        return [{"value": sc.id, "label": sc.name} for sc in obj.subcategories.all()]

    def get_subsubcategories(self, obj):
        return [{"value": ssc.id, "label": ssc.name} for ssc in obj.subsubcategories.all()]

    def get_products(self, obj):
        return [{"value": p.id, "label": p.product_name} for p in obj.products.all()]

class CouponUsageSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source='coupon.code', read_only=True)
    coupon_title = serializers.CharField(source='coupon.title', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = CouponUsage
        fields = [
            'id', 'coupon', 'coupon_code', 'coupon_title',
            'user', 'user_email', 'order', 'used_at',
            'discount_amount'
        ]
        read_only_fields = ['used_at']

class ApplyCouponSerializer(serializers.Serializer):
    coupon_code = serializers.CharField(max_length=50, required=True)

    def validate(self, data):
        request = self.context.get("request")
        cart_items = self.context.get("cart_items", [])

        coupon_code = data.get("coupon_code").upper()

        try:
            coupon = Coupon.objects.get(code=coupon_code)
        except Coupon.DoesNotExist:
            raise serializers.ValidationError("Invalid coupon code.")

        if not coupon.is_valid():
            raise serializers.ValidationError("This coupon is not valid or has expired.")

        applicable_items = []
        total_applicable_amount = Decimal("0.00")

        for item in cart_items:
            product_id = item.get("product_id")
            quantity = Decimal(str(item.get("quantity", 1)))
            price = Decimal(str(item.get("price", 0)))

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                continue

            if coupon.can_be_applied_to_product(product):
                line_total = price * quantity
                total_applicable_amount += line_total

                applicable_items.append({
                    "product": product,
                    "quantity": quantity,
                    "price": price,
                })

        if not applicable_items:
            raise serializers.ValidationError("Coupon not applicable to selected products.")

        if total_applicable_amount < coupon.min_order_value:
            raise serializers.ValidationError(
                f"Minimum order value should be ₹{coupon.min_order_value}"
            )

        data["coupon"] = coupon
        data["applicable_items"] = applicable_items
        data["total_applicable_amount"] = total_applicable_amount

        return data
    


class AvailableCouponSerializer(serializers.ModelSerializer):
    """Serializer for displaying available coupons at checkout"""
    discount_display = serializers.SerializerMethodField()
    validity_display = serializers.SerializerMethodField()
    conditions = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    
    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'title', 'coupon_type', 'discount_display',
            'min_order_value', 'max_discount', 'display_message',
            'validity_display', 'conditions', 'apply_on', 'is_valid'
        ]
    
    def get_discount_display(self, obj):
        if obj.coupon_type == 'percentage':
            return f"{obj.discount_percent}% OFF"
        elif obj.coupon_type == 'flat':
            return f"₹{obj.discount_amount} OFF"
        return ""
    
    def get_validity_display(self, obj):
        from django.utils.timezone import localtime
        return f"Valid till {localtime(obj.expire_date).strftime('%d %b %Y')}"
    
    def get_conditions(self, obj):
        conditions = []
        
        if obj.min_order_value > 0:
            conditions.append(f"Min. order: ₹{obj.min_order_value}")
        
        if obj.apply_on != 'all_products':
            if obj.apply_on == 'category':
                if obj.categories.exists():
                    category_names = [c.name for c in obj.categories.all()[:2]]
                    conditions.append(f"On {', '.join(category_names)} categories")
                elif obj.category:
                    conditions.append(f"On {obj.category.name} category")                   
            elif obj.apply_on == 'product':
                if obj.products.exists():
                    product_names = [p.product_name for p in obj.products.all()[:2]]
                    conditions.append(f"On {', '.join(product_names)}")
                elif obj.product:
                    conditions.append(f"On {obj.product.product_name}")
        
        if obj.max_count:
            remaining = obj.max_count - obj.used_count
            if remaining > 0:
                conditions.append(f"{remaining} uses left")
        
        return conditions
    
    def get_is_valid(self, obj):
        return obj.is_valid()