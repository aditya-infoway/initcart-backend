# ecommerce/serializers/product_serializers.py
import json
from decimal import Decimal
from rest_framework import serializers
from ecommerce.models.product import Product, ProductStock, ProductGallery
from ecommerce.models.vendor import Vendor, Brand
from ecommerce.models.category import Category, SubCategory, SubSubCategory

class ProductGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductGallery
        fields = ["id", "image"]


class ProductStockSerializer(serializers.ModelSerializer):
    variant_image = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = ProductStock
        fields = [
            "id", "mrp", "selling_price", "production_cost", 
            "discount_type", "discount_value", "tax", "stock_quantity",
            "color", "size", "barcode", "unit", "weight", 
            "maximum_order_quantity", "final_price", "variant_image",
            "platform_charge_percent", "vendor_receivable"  
        ]

# Vendor details serializer
class VendorDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ['id', 'business_name', 'vendor_type', 'email', 'phone', 'owner_name']


# Brand details serializer  
class BrandDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ['id', 'brand_name']


# Category details serializers
class CategoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'platform_charge']  #   ADDED platform_charge


class SubCategoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ['id', 'name']


class SubSubCategoryDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubSubCategory
        fields = ['id', 'name']


class ProductSerializer(serializers.ModelSerializer):
    gallery = ProductGallerySerializer(many=True, read_only=True)
    stocks = ProductStockSerializer(many=True, read_only=True)
    
    #   NEW: Add platform charge info in response
    platform_charge_info = serializers.SerializerMethodField()
    
    #   ADD THESE: Related field details with proper names
    vendor_details = VendorDetailSerializer(source='vendor', read_only=True)
    brand_details = BrandDetailSerializer(source='brand', read_only=True)
    category_details = CategoryDetailSerializer(source='category', read_only=True)
    subcategory_details = SubCategoryDetailSerializer(source='subcategory', read_only=True)
    subsubcategory_details = SubSubCategoryDetailSerializer(source='subsubcategory', read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", 
            "vendor", "vendor_details",
            "brand", "brand_details",  
            "product_name", "sku", 
            "category", "category_details",
            "subcategory", "subcategory_details",
            "subsubcategory", "subsubcategory_details",
            "product_type",
            "keywords", "short_description", "full_description", "product_video_url",
            "main_image", "thumbnail_image", "product_condition", 
            "manufacturing_date", "expiry_date", "return_policy",
            "estimated_delivery_time", "free_shipping", "status",
            "created_at", "updated_at", "gallery", "stocks",
            #   NEW FIELDS ADDED - description, specs, warranty, platform
            "description_features", "specifications", 
            "warranty_available", "warranty_period", "warranty_type", "warranty_description",
            "platform_charge_info"  #   NEW
        ]
        read_only_fields = ["vendor", "status", "created_at", "updated_at"]

    #   NEW METHOD - platform charge info
    def get_platform_charge_info(self, obj):
        """Return platform charge information for the product"""
        if obj.category:
            return {
                "category_id": obj.category.id,
                "category_name": obj.category.name,
                "platform_charge_percent": float(obj.category.platform_charge),
                "vendor_receivable": [
                    {
                        "stock_id": stock.id,
                        "selling_price": float(stock.selling_price),
                        "vendor_receivable": float(stock.vendor_receivable),
                        "platform_deduction": float(stock.selling_price - stock.vendor_receivable)
                    }
                    for stock in obj.stocks.all()
                ]
            }
        return None

    def create(self, validated_data):
        request = self.context.get('request')
        
        print(" === PRODUCT CREATE STARTED ===")
        
        #   VENDOR CHECK
        if not hasattr(request.user, 'vendor'):
            raise serializers.ValidationError({
                "error": "Vendor profile not found. Please complete your vendor profile setup."
            })
        
        vendor = request.user.vendor
        print(f"  Vendor found: {vendor.business_name} (ID: {vendor.id})")
        
        #   Extract description features from request
        description_features = request.data.get('description_features')
        if description_features:
            try:
                if isinstance(description_features, str):
                    validated_data['description_features'] = json.loads(description_features)
                else:
                    validated_data['description_features'] = description_features
            except:
                validated_data['description_features'] = []
        
        #   Extract specifications from request
        specifications = request.data.get('specifications')
        if specifications:
            try:
                if isinstance(specifications, str):
                    validated_data['specifications'] = json.loads(specifications)
                else:
                    validated_data['specifications'] = specifications
            except:
                validated_data['specifications'] = []
        
        #   Extract warranty from request
        warranty = request.data.get('warranty')
        if warranty:
            try:
                if isinstance(warranty, str):
                    warranty_data = json.loads(warranty)
                else:
                    warranty_data = warranty
                
                validated_data['warranty_available'] = warranty_data.get('available', False)
                validated_data['warranty_period'] = warranty_data.get('period', '')
                validated_data['warranty_type'] = warranty_data.get('type', 'Manufacturer Warranty')
                validated_data['warranty_description'] = warranty_data.get('description', '')
            except:
                pass
        
        #   Get platform charge from category (NEW)
        category = validated_data.get('category')
        platform_charge = category.platform_charge if category else Decimal('0.00')
        print(f" Platform charge for category: {platform_charge}%")
        
        #   Extract stocks data from request (with variant images)
        stocks_data = []
        variant_images = {}
        
        # First collect all variant images
        for key in request.FILES:
            if key.startswith('variant_images['):
                import re
                match = re.search(r'variant_images\[(\d+)\]', key)
                if match:
                    index = int(match.group(1))
                    variant_images[index] = request.FILES[key]
        
        index = 0
        while True:
            mrp = request.data.get(f'stocks[{index}][mrp]')
            if mrp is None:
                break
                
            stock_item = {
                'mrp': float(mrp or 0),
                'selling_price': float(request.data.get(f'stocks[{index}][selling_price]', 0) or 0),
                'production_cost': float(request.data.get(f'stocks[{index}][production_cost]', 0) or 0),
                'discount_type': request.data.get(f'stocks[{index}][discount_type]'),
                'discount_value': float(request.data.get(f'stocks[{index}][discount_value]', 0) or 0),
                'tax': float(request.data.get(f'stocks[{index}][tax]', 0) or 0),
                'stock_quantity': int(request.data.get(f'stocks[{index}][stock_quantity]', 0) or 0),
                'barcode': request.data.get(f'stocks[{index}][barcode]', ''),
                'unit': request.data.get(f'stocks[{index}][unit]', ''),
                'weight': request.data.get(f'stocks[{index}][weight]', ''),
                'color': request.data.get(f'stocks[{index}][color]', ''),
                'size': request.data.get(f'stocks[{index}][size]', ''),
                'maximum_order_quantity': int(request.data.get(f'stocks[{index}][maximum_order_quantity]', 1) or 1),
                #   NEW: Add platform charge to stock item
                'platform_charge_percent': platform_charge,
            }
            
            # Add variant image if exists for this index
            if index in variant_images:
                stock_item['variant_image'] = variant_images[index]
            
            stocks_data.append(stock_item)
            index += 1
        
        print(f" Stocks data: {len(stocks_data)} entries")
        
        #  Get files
        main_image = request.FILES.get('main_image')
        thumbnail_image = request.FILES.get('thumbnail_image')
        gallery_images = request.FILES.getlist('gallery_images')
        
        try:
            #  Create Product with all fields (including new ones)
            product = Product.objects.create(
                vendor=vendor,
                product_name=validated_data.get('product_name'),
                sku=validated_data.get('sku'),
                brand=validated_data.get('brand'),
                category=validated_data.get('category'),
                subcategory=validated_data.get('subcategory'),
                subsubcategory=validated_data.get('subsubcategory'),
                product_type=validated_data.get('product_type'),
                keywords=validated_data.get('keywords', ''),
                short_description=validated_data.get('short_description', ''),
                full_description=validated_data.get('full_description', ''),
                product_video_url=validated_data.get('product_video_url', ''),
                product_condition=validated_data.get('product_condition', 'New'),
                manufacturing_date=validated_data.get('manufacturing_date'),
                expiry_date=validated_data.get('expiry_date'),
                return_policy=validated_data.get('return_policy', ''),
                estimated_delivery_time=validated_data.get('estimated_delivery_time', ''),
                free_shipping=validated_data.get('free_shipping', False),
            
                description_features=validated_data.get('description_features', []),
                specifications=validated_data.get('specifications', []),
                warranty_available=validated_data.get('warranty_available', False),
                warranty_period=validated_data.get('warranty_period', ''),
                warranty_type=validated_data.get('warranty_type', 'Manufacturer Warranty'),
                warranty_description=validated_data.get('warranty_description', ''),
                status='pending',
                main_image=main_image,
                thumbnail_image=thumbnail_image
            )
            
            print(f" Product created successfully: {product.id}")
            
        except Exception as e:
            print(f" Product creation failed: {str(e)}")
            raise serializers.ValidationError({"error": f"Product creation failed: {str(e)}"})
        
        #  Create Stock entries with variant images and platform charge
        try:
            for stock_item in stocks_data:
                # Clean empty strings
                for key in ['discount_type', 'barcode', 'unit', 'weight', 'color', 'size']:
                    if stock_item.get(key) == '':
                        stock_item[key] = None
                
                # Extract variant image if present
                variant_image = stock_item.pop('variant_image', None)
                
                # Create stock without variant image first
                stock = ProductStock.objects.create(product=product, **stock_item)
                
                # Add variant image if exists
                if variant_image:
                    stock.variant_image = variant_image
                    stock.save()
                
                print(f"   Stock {stock.id}: Vendor receivable = ₹{stock.vendor_receivable}")
            
            print(f" {len(stocks_data)} stock entries created")
            
        except Exception as e:
            print(f" Stock creation failed: {str(e)}")
            product.delete()
            raise serializers.ValidationError({"error": f"Stock creation failed: {str(e)}"})
    
        #  Create Gallery images
        try:
            for image_file in gallery_images:
                ProductGallery.objects.create(product=product, image=image_file)
            
            print(f" {len(gallery_images)} gallery images created")
            
        except Exception as e:
            print(f" Gallery creation failed: {str(e)}")
        
        return product

    def update(self, instance, validated_data):
        request = self.context.get('request')
        
        print(" === PRODUCT UPDATE STARTED ===")
        print(f"Updating product: {instance.id} - {instance.product_name}")
        print(f"Current status: {instance.status}")
        
        #  CRITICAL: If product was approved, set status to pending after edit
        if instance.status == "approved":
            instance.status = "pending"
            print(" Status changed from 'approved' to 'pending'")
        
        #  Extract description features from request
        description_features = request.data.get('description_features')
        if description_features:
            try:
                if isinstance(description_features, str):
                    validated_data['description_features'] = json.loads(description_features)
                else:
                    validated_data['description_features'] = description_features
            except:
                pass
        
        # Extract specifications from request
        specifications = request.data.get('specifications')
        if specifications:
            try:
                if isinstance(specifications, str):
                    validated_data['specifications'] = json.loads(specifications)
                else:
                    validated_data['specifications'] = specifications
            except:
                pass
        
        # Extract warranty from request
        warranty = request.data.get('warranty')
        if warranty:
            try:
                if isinstance(warranty, str):
                    warranty_data = json.loads(warranty)
                else:
                    warranty_data = warranty
                
                validated_data['warranty_available'] = warranty_data.get('available', False)
                validated_data['warranty_period'] = warranty_data.get('period', '')
                validated_data['warranty_type'] = warranty_data.get('type', 'Manufacturer Warranty')
                validated_data['warranty_description'] = warranty_data.get('description', '')
            except:
                pass
        
        # Get platform charge from category (might have changed)
        category = validated_data.get('category', instance.category)
        platform_charge = category.platform_charge if category else Decimal('0.00')
        print(f"Platform charge for category: {platform_charge}%")
        
        # Extract stocks data from request (with variant images)
        stocks_data = []
        variant_images = {}
        
        # First collect all variant images
        for key in request.FILES:
            if key.startswith('variant_images['):
                import re
                match = re.search(r'variant_images\[(\d+)\]', key)
                if match:
                    index = int(match.group(1))
                    variant_images[index] = request.FILES[key]
        
        index = 0
        while True:
            mrp = request.data.get(f'stocks[{index}][mrp]')
            if mrp is None:
                break
                
            stock_item = {
                'mrp': float(mrp or 0),
                'selling_price': float(request.data.get(f'stocks[{index}][selling_price]', 0) or 0),
                'production_cost': float(request.data.get(f'stocks[{index}][production_cost]', 0) or 0),
                'discount_type': request.data.get(f'stocks[{index}][discount_type]'),
                'discount_value': float(request.data.get(f'stocks[{index}][discount_value]', 0) or 0),
                'tax': float(request.data.get(f'stocks[{index}][tax]', 0) or 0),
                'stock_quantity': int(request.data.get(f'stocks[{index}][stock_quantity]', 0) or 0),
                'barcode': request.data.get(f'stocks[{index}][barcode]', ''),
                'unit': request.data.get(f'stocks[{index}][unit]', ''),
                'weight': request.data.get(f'stocks[{index}][weight]', ''),
                'color': request.data.get(f'stocks[{index}][color]', ''),
                'size': request.data.get(f'stocks[{index}][size]', ''),
                'maximum_order_quantity': int(request.data.get(f'stocks[{index}][maximum_order_quantity]', 1) or 1),
                'variant_image_url': request.data.get(f'stocks[{index}][variant_image_url]', ''),
                #  NEW: Add platform charge to stock item
                'platform_charge_percent': platform_charge,
            }
            
            # Add variant image if exists for this index
            if index in variant_images:
                stock_item['variant_image'] = variant_images[index]
            
            stocks_data.append(stock_item)
            index += 1
        
        print(f" Stocks data for update: {len(stocks_data)} entries")
        
        #  Get files
        main_image = request.FILES.get('main_image')
        thumbnail_image = request.FILES.get('thumbnail_image')
        gallery_images = request.FILES.getlist('gallery_images')
        
        try:
            #  Update basic fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            
            #  Update images if new files are provided
            if main_image:
                instance.main_image = main_image
            if thumbnail_image:
                instance.thumbnail_image = thumbnail_image
            
            instance.save()
            print(f" Product basic info updated: {instance.id}")
            
        except Exception as e:
            print(f" Product update failed: {str(e)}")
            raise serializers.ValidationError({"error": f"Product update failed: {str(e)}"})
        
        #  Update Stock entries - Delete old and create new (with variant images and platform charge)
        try:
            # Delete existing stocks
            instance.stocks.all().delete()
            print(f"Deleted existing stocks")
            
            # Create new stocks
            for stock_item in stocks_data:
                # Clean empty strings
                for key in ['discount_type', 'barcode', 'unit', 'weight', 'color', 'size']:
                    if stock_item.get(key) == '':
                        stock_item[key] = None
                
                # Extract variant image if present
                variant_image = stock_item.pop('variant_image', None)
                variant_image_url = stock_item.pop('variant_image_url', None)
                
                # Create stock
                stock = ProductStock.objects.create(product=instance, **stock_item)
                
                # Add variant image if exists
                if variant_image:
                    stock.variant_image = variant_image
                    stock.save()
                
                print(f"   Stock {stock.id}: Vendor receivable = ₹{stock.vendor_receivable}")
            
            print(f" {len(stocks_data)} new stock entries created")
            
        except Exception as e:
            print(f" Stock update failed: {str(e)}")
            raise serializers.ValidationError({"error": f"Stock update failed: {str(e)}"})
        
        #  Update Gallery images - Add new ones
        try:
            for image_file in gallery_images:
                ProductGallery.objects.create(product=instance, image=image_file)
            
            print(f" {len(gallery_images)} new gallery images added")
            
        except Exception as e:
            print(f" Gallery update failed: {str(e)}")
        
        print(" === PRODUCT UPDATE COMPLETED ===")
        return instance
    
    