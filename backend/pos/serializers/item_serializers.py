# pos/serializers/item_serializers.py
from rest_framework import serializers
from pos.models.items import items, itemvariants
from ecommerce.models.category import Category, SubCategory, SubSubCategory
from ecommerce.models.vendor import Brand
from ecommerce.models.product import Product, ProductStock
from pos.models.group_unit import ItemGroup, ItemUnit
from pos.serializers.group_unit_serializers import ItemGroupSerializer, ItemUnitSerializer
import json
import random
import string
from django.db.models.deletion import ProtectedError
from pos.serializers.mixins_serializers import CreatedByReadMixin

class VariantSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    variant_image = serializers.ImageField(required=False, allow_null=True)
    variant_image_url = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = itemvariants
        fields = [
            'id', 'purchasePrice', 'salesPrice', 'mrp', 'barcode', 
            'opStock', 'basicAmount', 'discountAmount', 'taxAmount', 
            'netValue', 'current_stock', 'size', 'color', 'srno', 
            'warrantydate', 'variant_image', 'variant_image_url',
            'branchPrice',
        ]
    
    def validate_barcode(self, value):
        if value:
            value = str(value)
            if not value.isalnum():
                raise serializers.ValidationError("Barcode can only contain letters and numbers")
            
            request = self.context.get('request')
            is_update = self.context.get('is_update', False)
            item_id = self.context.get('item_id')
            
            if request and hasattr(request, 'user') and request.user:
                branch = request.user.get_effective_branch()
                if branch:
                    qs = itemvariants.objects.filter(barcode=value, item__branch=branch)
                    
                    if self.instance and self.instance.pk:
                        # Serializer was instantiated with an existing object
                        qs = qs.exclude(id=self.instance.pk)
                    elif is_update and item_id:
                        # Top-level validation during update — exclude ALL variants
                        # of this item because they all legitimately own their barcodes
                        qs = qs.exclude(item_id=item_id)
                    else:
                        # New item create — exclude same item's other variants
                        if item_id:
                            qs = qs.exclude(item_id=item_id)
                    
                    if qs.exists():
                        raise serializers.ValidationError(
                            f"Barcode '{value}' already exists in this branch."
                        )
        
        return value
    def validate(self, data):
        """Validate MRP vs Sales Price"""
        mrp = data.get('mrp')
        sales_price = data.get('salesPrice')
        
        if mrp is not None and sales_price is not None:
            #  MRP can be greater than or equal to Sales Price
            # Sales Price cannot be greater than MRP
            if sales_price > mrp:
                raise serializers.ValidationError({
                    "salesPrice": "Sales Price cannot be greater than MRP"
                })
        
        return data
    
    def get_variant_image_url(self, obj):
        if obj.variant_image:
            return obj.variant_image.url
        return None

class itemSerializers(serializers.ModelSerializer):
    branch_fields = serializers.JSONField(required=False, write_only=True)
    variants = VariantSerializer(many=True, required=False)
    brand = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    category = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    subCategory = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    subSubCategory = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    group_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    unit_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    group_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    unit_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = items
        fields = '__all__'
        read_only_fields = ['branch', 'linked_product', 'website_status', 'group', 'unit']


    def validate(self, data):
        request = self.context.get("request", None)
        user = getattr(request, "user", None)

        branch = user.get_effective_branch() if user else None
        if not branch:
            raise serializers.ValidationError(
                {"branch": "User has no branch assigned or request is not authenticated"}
            )

        branch_type = branch.branch_type

        BRANCH_REQUIRED_FIELDS = {
            "Fashion": ["size", "color"],
            "Mart": ["size"],
            "Electronics": ["size", "color", "srno", "warrantydate"],
        }

        required_fields = BRANCH_REQUIRED_FIELDS.get(branch_type, [])
        branch_fields = data.get("branch_fields") or {}
        errors = {}

        for field in required_fields:
            value = branch_fields.get(field)
            if value in [None, "", []]:
                errors[field] = f"{field} is required for {branch_type} items"

        if errors:
            raise serializers.ValidationError(errors)

        return data

    def create(self, validated_data):
        print(f"=== CREATE CALLED ===")
        import traceback
        traceback.print_stack() 
        
        # ✅ Use request only once
        request = self.context.get("request")         
        if request and request.user and request.user.is_authenticated:  
            validated_data["created_by"] = request.user  
        
        variants_data = validated_data.pop("variants", [])
        group_id = validated_data.pop("group_id", None)
        unit_id = validated_data.pop("unit_id", None)
        group_name = validated_data.pop("group_name", None)
        unit_name = validated_data.pop("unit_name", None)
        branch_fields = validated_data.pop("branch_fields", None)
        
        # ✅ Use the existing request variable - don't redefine it
        user = getattr(request, "user", None)  # Use request from above
        
        # Handle branch fields (size, color, srno, warrantydate)
        if branch_fields:
            for key, value in branch_fields.items():
                validated_data[key] = value
            
        # Handle brand/category/subCategory/subSubCategory
        def handle(value, fk_field, text_field):
            if value in [None, ""]:
                return
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
                validated_data[fk_field] = int(value)
                validated_data[text_field] = None
            else:
                validated_data[text_field] = value
                validated_data[fk_field] = None

        brand_val = validated_data.pop("brand", None)
        category_val = validated_data.pop("category", None)
        subCategory_val = validated_data.pop("subCategory", None)
        subSubCategory_val = validated_data.pop("subSubCategory", None)
        
        handle(brand_val, "c_brand_id", "brand")
        handle(category_val, "c_category_id", "category")
        handle(subCategory_val, "c_subCategory_id", "subCategory")
        handle(subSubCategory_val, "c_subSubCategory_id", "subSubCategory")

        user_branch = user.get_effective_branch() if user else None
        if user_branch:
            validated_data["branch"] = user_branch
            
            # Handle group
            if group_id:
                try:
                    validated_data["group"] = ItemGroup.objects.get(id=group_id, branch=user_branch)
                except ItemGroup.DoesNotExist:
                    pass
            elif group_name:
                group, created = ItemGroup.objects.get_or_create(
                    name=group_name,
                    branch=user_branch,
                    defaults={'description': f'Created from item {validated_data.get("itemName", "")}'}
                )
                validated_data["group"] = group
            
            # Handle unit
            if unit_id:
                try:
                    validated_data["unit"] = ItemUnit.objects.get(id=unit_id)
                except ItemUnit.DoesNotExist:
                    pass
            elif unit_name:
                unit, created = ItemUnit.objects.get_or_create(
                    name=unit_name,
                    defaults={
                        'symbol': unit_name[:3].lower(),
                        'unit_type': 'count',
                        'supports_fractional': False,
                    }
                )
                validated_data["unit"] = unit

        item = items.objects.create(**validated_data)

        # Save each variant
        # Save each variant with context
        for v_data in variants_data:
            variant_serializer = VariantSerializer(
                data=v_data, 
                context={
                    "request": self.context.get("request"),
                    "item_id": item.id,
                }
            )
            if variant_serializer.is_valid():
                variant_serializer.save(item=item)
            else:
                raise serializers.ValidationError(variant_serializer.errors)

        return item

    def update(self, instance, validated_data):
        """Update method - also handles variants"""
        
        print(f"=== UPDATE CALLED ===")
        print(f"Instance ID: {instance.id}")
        variants_in_data = validated_data.get('variants', [])
        print(f"Variants count in validated_data: {len(variants_in_data) if variants_in_data else 0}")
        
        variants_data = validated_data.pop("variants", None)
        
        group_id = validated_data.pop("group_id", None)
        unit_id = validated_data.pop("unit_id", None)
        group_name = validated_data.pop("group_name", None)
        unit_name = validated_data.pop("unit_name", None)
        branch_fields = validated_data.pop("branch_fields", None)
        
        request = self.context.get("request")
        user = getattr(request, "user", None)
        user_branch = user.get_effective_branch() if user else None 
        
        if branch_fields:
            for key, value in branch_fields.items():
                setattr(instance, key, value)
        
        def handle(value, fk_field, text_field):
            if value in [None, ""]:
                setattr(instance, fk_field, None)
                setattr(instance, text_field, None)
            elif isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
                setattr(instance, fk_field, int(value))
                setattr(instance, text_field, None)
            else:
                setattr(instance, text_field, value)
                setattr(instance, fk_field, None)

        brand_val = validated_data.pop("brand", None) if "brand" in validated_data else None
        category_val = validated_data.pop("category", None) if "category" in validated_data else None
        subCategory_val = validated_data.pop("subCategory", None) if "subCategory" in validated_data else None
        subSubCategory_val = validated_data.pop("subSubCategory", None) if "subSubCategory" in validated_data else None
        
        handle(brand_val, "c_brand_id", "brand")
        handle(category_val, "c_category_id", "category")
        handle(subCategory_val, "c_subCategory_id", "subCategory")
        handle(subSubCategory_val, "c_subSubCategory_id", "subSubCategory")
        
        if group_id is not None or group_name is not None:
            if group_id:
                try:
                    instance.group = ItemGroup.objects.get(id=group_id, branch=user_branch)
                except ItemGroup.DoesNotExist:
                    instance.group = None
            elif group_name:
                group, created = ItemGroup.objects.get_or_create(
                    name=group_name,
                    branch=user_branch,
                    defaults={'description': f'Updated from item {instance.itemName}'}
                )
                instance.group = group
            else:
                instance.group = None
        
        if unit_id is not None or unit_name is not None:
            if unit_id:
                try:
                    instance.unit = ItemUnit.objects.get(id=unit_id)
                except ItemUnit.DoesNotExist:
                    instance.unit = None
            elif unit_name:
                unit, created = ItemUnit.objects.get_or_create(
                    name=unit_name,
                    defaults={
                        'symbol': unit_name[:3].lower(),
                        'unit_type': 'count', 
                        'supports_fractional': False,
                    }
                )
                instance.unit = unit
            else:
                instance.unit = None
        
        for attr, value in validated_data.items():
            if attr not in ['group', 'unit', 'c_brand', 'c_category', 'c_subCategory', 'c_subSubCategory']:
                setattr(instance, attr, value)
        
        instance.save()
        
        # ✅ FIX: Variants handle karo - sirf incoming variants update/create karo
        # aur baaki sab delete karo
        if variants_data is not None:
            incoming_variant_ids = []
            
            for v_data in variants_data:
                variant_id = v_data.get('id')
                
                # ✅ FIX: Sirf valid positive DB IDs treat karo existing ke taur pe
                # Negative IDs (frontend ke temporary IDs) ko new variant maano
                is_existing = (
                    variant_id is not None and 
                    isinstance(variant_id, int) and 
                    variant_id > 0
                )
                
                if is_existing:
                    incoming_variant_ids.append(variant_id)
                    try:
                        variant = itemvariants.objects.get(id=variant_id, item=instance)
                        print(f"DEBUG variant.id={variant.id}, variant.barcode={variant.barcode}")
                        # ✅ Existing variant update karo
                        v_data_clean = {k: v for k, v in v_data.items() if k != 'id'}
                        variant_serializer = VariantSerializer(
                            variant, 
                            data=v_data_clean, 
                            partial=True,
                            context={
                                "request": self.context.get("request"),
                                "item_id": instance.id,
                            }
                        )
                        if variant_serializer.is_valid():
                            variant_serializer.save()
                        else:
                            raise serializers.ValidationError(variant_serializer.errors)
                    except itemvariants.DoesNotExist:
                        # ✅ Frontend ne existing variant id bheja tha, lekin wo id is
                        # item ke against exist nahi karta — silently naya variant
                        # banana galat hai (isse duplicate variant ban jaate hain).
                        # Iski jagah clear error do taaki asli wajah pata chale.
                        raise serializers.ValidationError({
                            "variants": f"Variant id {variant_id} not found for this item. "
                                        f"Please refresh and try editing again."
                        })
                else:
                    # ✅ Naya variant create karo (negative ID ya no ID)
                    v_data_clean = {k: v for k, v in v_data.items() if k != 'id'}
                    variant_serializer = VariantSerializer(
                        data=v_data_clean,
                        context={
                            "request": self.context.get("request"),
                            "item_id": instance.id,
                        }
                    )
                    if variant_serializer.is_valid():
                        new_variant = variant_serializer.save(item=instance)
                        incoming_variant_ids.append(new_variant.id)
                    else:
                        raise serializers.ValidationError(variant_serializer.errors)
            
            # ✅ YEH LINE SABSE IMPORTANT THI JO MISSING THI:
            # Jo variants incoming mein nahi hain, unhe delete karo
            variants_to_remove = instance.variants.exclude(id__in=incoming_variant_ids)
            for variant in variants_to_remove:
                try:
                    variant.delete()
                except ProtectedError:
                    continue

        return instance
        

# Update ItemWithVariantsSerializer
class ItemWithVariantsSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    brand = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    subCategory = serializers.SerializerMethodField()
    subsubCategory = serializers.SerializerMethodField()
    variants = VariantSerializer(many=True, read_only=True)
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    
    # Add these for group and unit
    group = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    
    class Meta:
        model = items
        fields = [
            "id",
            "entry_type",
            "itemName",
            "branch_name",
            "group",
            "unit",
            "hsnCode",
            "taxSlab",
            "brand",
            "category",
            "subCategory",
            "subsubCategory",
            "variants",
            "short_description",
            "full_description",
            "keywords",
            "main_image",
            "thumbnail_image",
            "gallery",
            "product_condition",
            "return_policy",
            "estimated_delivery_time",
            "free_shipping",
            "warranty_available",
            "warranty_period",
            "warranty_type",
            "warranty_description",
            "description_features",
            "specifications",
            "website_display",
            "website_status",
            "linked_product",
            "created_at",
            "updated_at",
            "created_by",
            "created_by_name",
        ]


    def get_brand(self, obj):
        """Return brand object with id and name"""
        if obj.c_brand:
            return {"id": obj.c_brand.id, "name": obj.c_brand.brand_name}
        if obj.brand:
            return {"id": None, "name": obj.brand}
        return None

    def get_category(self, obj):
        """Return category object with id and name"""
        if obj.c_category:
            return {"id": obj.c_category.id, "name": obj.c_category.name}
        if obj.category:
            return {"id": None, "name": obj.category}
        return None

    def get_subCategory(self, obj):
        """Return subcategory object with id and name"""
        if obj.c_subCategory:
            return {"id": obj.c_subCategory.id, "name": obj.c_subCategory.name}
        if obj.subCategory:
            return {"id": None, "name": obj.subCategory}
        return None

    def get_subsubCategory(self, obj):
        """Return subsubcategory object with id and name"""
        if obj.c_subSubCategory:
            return {"id": obj.c_subSubCategory.id, "name": obj.c_subSubCategory.name}
        if obj.subSubCategory:
            return {"id": None, "name": obj.subSubCategory}
        return None
    def get_group(self, obj):
        if obj.group:
            return {"id": obj.group.id, "name": obj.group.name}
        return None
        
    def get_unit(self, obj):
        if obj.unit:
            return {
                "id": obj.unit.id,
                "name": obj.unit.name,
                "symbol": obj.unit.symbol,
                "supports_fractional": obj.unit.supports_fractional,  # ✅ yeh add karo
            }
        return None
# pos/serializers/item_serializers.py - Update AdminWebsiteItemListSerializer

class AdminWebsiteItemListSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    variants_count = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    original_price = serializers.SerializerMethodField()
    
    # Category fields as strings
    category = serializers.SerializerMethodField()
    subCategory = serializers.SerializerMethodField()
    
    # Include all description and specification fields
    short_description = serializers.CharField(read_only=True)
    full_description = serializers.CharField(read_only=True)
    description_features = serializers.JSONField(read_only=True)
    specifications = serializers.JSONField(read_only=True)
    
    # Warranty fields
    warranty_available = serializers.BooleanField(read_only=True)
    warranty_period = serializers.CharField(read_only=True)
    warranty_type = serializers.CharField(read_only=True)
    warranty_description = serializers.CharField(read_only=True)
    
    # Shipping fields
    return_policy = serializers.CharField(read_only=True)
    estimated_delivery_time = serializers.CharField(read_only=True)
    free_shipping = serializers.BooleanField(read_only=True)
    product_condition = serializers.CharField(read_only=True)
    
    # Variants with all fields including images
    variants = VariantSerializer(many=True, read_only=True)
    
    class Meta:
        model = items
        fields = [
            'id', 'itemName', 'branch_name', 'category', 'subCategory',
            'website_status', 'created_at', 'updated_at',
            'variants_count', 'total_stock', 'final_price', 'original_price',
            'main_image', 'thumbnail_image', 'linked_product',
            'short_description', 'full_description', 'description_features',
            'specifications', 'warranty_available', 'warranty_period',
            'warranty_type', 'warranty_description', 'return_policy',
            'estimated_delivery_time', 'free_shipping', 'product_condition',
            'variants', "created_by", "created_by_name",
        ]
    
    def get_variants_count(self, obj):
        return obj.variants.count()
    
    def get_total_stock(self, obj):
        return sum(variant.current_stock or variant.opStock for variant in obj.variants.all())
    
    def get_final_price(self, obj):
        first_variant = obj.variants.first()
        if not first_variant:
            return 0
        selling_price = float(first_variant.salesPrice)
        tax_rate = float(obj.taxSlab.replace('%', '')) if obj.taxSlab else 0
        if tax_rate > 0:
            tax_amount = (selling_price * tax_rate) / 100
            return round(selling_price + tax_amount, 2)
        return round(selling_price, 2)
    
    def get_original_price(self, obj):
        first_variant = obj.variants.first()
        if first_variant:
            return round(float(first_variant.salesPrice), 2)
        return 0
    
    def get_category(self, obj):
        if obj.c_category:
            return obj.c_category.name
        return obj.category or None
    
    def get_subCategory(self, obj):
        if obj.c_subCategory:
            return obj.c_subCategory.name
        return obj.subCategory or None
    
class WebsiteItemListSerializer(CreatedByReadMixin, serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    variants_count = serializers.SerializerMethodField()
    total_stock = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    original_price = serializers.SerializerMethodField()
    
    # Category fields as strings (not objects)
    category = serializers.SerializerMethodField()
    subCategory = serializers.SerializerMethodField()
    variants = VariantSerializer(many=True, read_only=True)
    # Platform charge fields
    platform_charge_percent = serializers.SerializerMethodField()
    vendor_receivable = serializers.SerializerMethodField()
    platform_deduction = serializers.SerializerMethodField()
    
    # Completion fields
    has_description = serializers.SerializerMethodField()
    has_images = serializers.SerializerMethodField()
    has_specifications = serializers.SerializerMethodField()
    has_warranty = serializers.SerializerMethodField()
    completion_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = items
        fields = [
            'id', 'itemName', 'branch_name', 'category', 'subCategory',
            'website_status', 'created_at', 'variants_count', 'total_stock',
            'final_price', 'original_price', 'main_image', 'thumbnail_image', 
            'short_description', 'full_description', 'has_description', 'has_images', 
            'has_specifications', 'has_warranty', 'completion_percentage',
            'platform_charge_percent', 'vendor_receivable', 'platform_deduction',
            'variants',"created_by","created_by_name",
        ]
    
    def get_variants_count(self, obj):
        return obj.variants.count()
    
    def get_total_stock(self, obj):
        return sum(variant.current_stock or variant.opStock for variant in obj.variants.all())
    
    def get_final_price(self, obj):
        first_variant = obj.variants.first()
        if not first_variant:
            return 0
        selling_price = float(first_variant.salesPrice)
        tax_rate = float(obj.taxSlab.replace('%', '')) if obj.taxSlab else 0
        if tax_rate > 0:
            tax_amount = (selling_price * tax_rate) / 100
            return round(selling_price + tax_amount, 2)
        return round(selling_price, 2)
    
    def get_original_price(self, obj):
        first_variant = obj.variants.first()
        if first_variant:
            return round(float(first_variant.salesPrice), 2)
        return 0
    
    def get_category(self, obj):
        """Return category name as string"""
        if obj.c_category:
            return obj.c_category.name
        return obj.category or None
    
    def get_subCategory(self, obj):
        """Return subcategory name as string"""
        if obj.c_subCategory:
            return obj.c_subCategory.name
        return obj.subCategory or None
    
    def get_platform_charge_percent(self, obj):
        if obj.c_category:
            return float(obj.c_category.platform_charge)
        return 0
    
    def get_vendor_receivable(self, obj):
        final_price = self.get_final_price(obj)
        platform_charge = self.get_platform_charge_percent(obj)
        if platform_charge > 0 and final_price > 0:
            deduction = (final_price * platform_charge) / 100
            return round(final_price - deduction, 2)
        return final_price
    
    def get_platform_deduction(self, obj):
        final_price = self.get_final_price(obj)
        platform_charge = self.get_platform_charge_percent(obj)
        if platform_charge > 0 and final_price > 0:
            return round((final_price * platform_charge) / 100, 2)
        return 0
    
    def get_has_description(self, obj):
        return bool(obj.short_description or obj.full_description)
    
    def get_has_images(self, obj):
        return bool(obj.main_image or obj.thumbnail_image)
    
    def get_has_specifications(self, obj):
        return bool(obj.specifications and len(obj.specifications) > 0)
    
    def get_has_warranty(self, obj):
        return obj.warranty_available
    
    def get_completion_percentage(self, obj):
        completed = 0
        total = 8
        if obj.short_description:
            completed += 1
        if obj.full_description:
            completed += 1
        if obj.main_image:
            completed += 1
        if obj.thumbnail_image:
            completed += 1
        if obj.description_features and len(obj.description_features) > 0:
            completed += 1
        if obj.specifications and len(obj.specifications) > 0:
            completed += 1
        if obj.return_policy:
            completed += 1
        if obj.warranty_available:
            completed += 1
        return int((completed / total) * 100)


class ApproveItemToProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = items
        fields = ['id', 'itemName', 'website_status', 'linked_product']
        read_only_fields = ['linked_product']
    
    def update(self, instance, validated_data):
        new_status = validated_data.get('website_status', instance.website_status)
        
        print(f"🔄 === APPROVAL PROCESS STARTED ===")
        print(f"Item: {instance.id} - {instance.itemName}")
        print(f"Current status: {instance.website_status} -> New status: {new_status}")
        print(f"Has linked product: {instance.linked_product is not None}")
        
        if new_status == 'approved':
            # Case 1: First time approval - no product exists
            if not instance.linked_product:
                try:
                    # Get vendor from branch user
                    vendor = instance.get_vendor_for_branch()
                    if not vendor:
                        raise serializers.ValidationError(
                            {"error": "No vendor associated with this branch"}
                        )
                    
                    print(f"    Creating new product for item: {instance.id}")
                    
                    # Get category FK
                    category = instance.c_category
                    subcategory = instance.c_subCategory
                    subsubcategory = instance.c_subSubCategory
                    brand = instance.c_brand
                    
                    # Parse JSON fields
                    description_features = instance.description_features
                    if isinstance(description_features, str):
                        try:
                            description_features = json.loads(description_features)
                        except:
                            description_features = []
                    
                    specifications = instance.specifications
                    if isinstance(specifications, str):
                        try:
                            specifications = json.loads(specifications)
                        except:
                            specifications = []
                    
                    # Generate unique SKU
                    random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                    sku = f"ITEM-{instance.id}-{instance.itemName[:8]}-{random_suffix}".upper().replace(' ', '_')
                    
                    # Create product
                    product = Product.objects.create(
                        vendor=vendor,
                        product_name=instance.itemName,
                        sku=sku,
                        brand=brand,
                        category=category,
                        subcategory=subcategory,
                        subsubcategory=subsubcategory,
                        product_type='variant' if instance.variants.count() > 1 else 'simple',
                        keywords=instance.keywords or '',
                        short_description=instance.short_description or '',
                        full_description=instance.full_description or '',
                        product_condition=instance.product_condition or 'New',
                        return_policy=instance.return_policy or '',
                        estimated_delivery_time=instance.estimated_delivery_time or '',
                        free_shipping=instance.free_shipping,
                        description_features=description_features,
                        specifications=specifications,
                        warranty_available=instance.warranty_available,
                        warranty_period=instance.warranty_period,
                        warranty_type=instance.warranty_type,
                        warranty_description=instance.warranty_description,
                        status='approved',
                        main_image=instance.main_image,
                        thumbnail_image=instance.thumbnail_image
                    )
                    
                    print(f"    Product created: ID {product.id}")
                    
                    # Create stock entries for each variant
                    tax_rate = float(instance.taxSlab.replace('%', '')) if instance.taxSlab else 0
                    platform_charge = category.platform_charge if category else 0
                    
                    for variant in instance.variants.all():
                        ProductStock.objects.create(
                            product=product,
                            mrp=variant.mrp,
                            selling_price=variant.salesPrice,
                            tax=tax_rate,
                            stock_quantity=variant.current_stock or variant.opStock,
                            barcode=str(variant.barcode) if variant.barcode else '',
                            unit=instance.unit or '',
                            weight='',
                            color=variant.color or '',
                            size=variant.size or '',
                            maximum_order_quantity=10,
                            final_price=variant.salesPrice,
                            variant_image=variant.variant_image,
                            platform_charge_percent=platform_charge
                        )
                    
                    # Link product to item
                    instance.linked_product = product
                    
                except Exception as e:
                    print(f"❌ Error creating product: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    raise serializers.ValidationError(
                        {"error": f"Failed to create product: {str(e)}"}
                    )
            
            # Case 2: Re-approval - product exists
            elif instance.linked_product:
                print(f"🔄 Re-approving existing product: {instance.linked_product.id}")
                
                # Update existing product with latest item data
                product = instance.linked_product
                
                # Parse JSON fields
                description_features = instance.description_features
                if isinstance(description_features, str):
                    try:
                        description_features = json.loads(description_features)
                    except:
                        description_features = []
                
                specifications = instance.specifications
                if isinstance(specifications, str):
                    try:
                        specifications = json.loads(specifications)
                    except:
                        specifications = []
                
                # Update product fields
                product.product_name = instance.itemName
                product.brand = instance.c_brand
                product.category = instance.c_category
                product.subcategory = instance.c_subCategory
                product.subsubcategory = instance.c_subSubCategory
                product.keywords = instance.keywords or ''
                product.short_description = instance.short_description or ''
                product.full_description = instance.full_description or ''
                product.product_condition = instance.product_condition or 'New'
                product.return_policy = instance.return_policy or ''
                product.estimated_delivery_time = instance.estimated_delivery_time or ''
                product.free_shipping = instance.free_shipping
                product.description_features = description_features
                product.specifications = specifications
                product.warranty_available = instance.warranty_available
                product.warranty_period = instance.warranty_period
                product.warranty_type = instance.warranty_type
                product.warranty_description = instance.warranty_description
                
                # Update images if new ones provided
                if instance.main_image:
                    product.main_image = instance.main_image
                if instance.thumbnail_image:
                    product.thumbnail_image = instance.thumbnail_image
                
                # Set product status back to approved
                product.status = 'approved'
                product.save()
                
                print(f"    Product {product.id} updated and approved")
                
                # Update stocks - delete old and create new
                product.stocks.all().delete()
                
                tax_rate = float(instance.taxSlab.replace('%', '')) if instance.taxSlab else 0
                platform_charge = instance.c_category.platform_charge if instance.c_category else 0
                
                for variant in instance.variants.all():
                    ProductStock.objects.create(
                        product=product,
                        mrp=variant.mrp,
                        selling_price=variant.salesPrice,
                        tax=tax_rate,
                        stock_quantity=variant.current_stock or variant.opStock,
                        barcode=str(variant.barcode) if variant.barcode else '',
                        unit=instance.unit or '',
                        weight='',
                        color=variant.color or '',
                        size=variant.size or '',
                        maximum_order_quantity=10,
                        final_price=variant.salesPrice,
                        variant_image=variant.variant_image,
                        platform_charge_percent=platform_charge
                    )
                
                print(f"    Stocks updated for product {product.id}")
            
            # Update item status to approved
            instance.website_status = 'approved'
            instance.save()
            
            print(f"🎉 ITEM APPROVED SUCCESSFULLY!")
            
        elif new_status == 'rejected':
            instance.website_status = 'rejected'
            instance.save()
            print(f"❌ Item {instance.id} rejected")
        else:
            instance.website_status = new_status
            instance.save()
            print(f"ℹ️ Item {instance.id} status updated to {new_status}")
        
        return instance


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class SubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ["id", "name", "category"]


class SubSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubSubCategory
        fields = ["id", "name", "subcategory"]


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "brand_name"]
        
        
