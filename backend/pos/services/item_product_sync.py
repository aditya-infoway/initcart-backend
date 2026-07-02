import os  # ✅ ADD THIS IMPORT
from django.db import transaction
from decimal import Decimal
import json
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from core import settings

class ItemToProductSyncService:
    """Service to sync items to products for website display"""
    
    @staticmethod
    @transaction.atomic
    def sync_item_to_product(item_id):
        """
        Sync a single item to product if website_display is True
        Returns: (success, message, product_id)
        """
        from pos.models.items import items
        from ecommerce.models.product import Product, ProductStock, ProductGallery
        import os
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        from django.conf import settings
        
        try:
            item = items.objects.select_related(
                'branch', 'c_brand', 'c_category', 'c_subCategory', 'c_subSubCategory'
            ).prefetch_related('variants').get(id=item_id)
            
            if not item.website_display:
                return False, "Item not marked for website display", None
            
            if item.linked_product:
                return False, "Item already has a linked product", item.linked_product.id
            
            # Get vendor from branch user
            if not item.branch or not hasattr(item.branch.user, 'vendor'):
                return False, "No vendor associated with this branch", None
            
            vendor = item.branch.user.vendor
            
            # Get platform charge from category
            platform_charge = item.c_category.platform_charge if item.c_category else Decimal('0.00')
            
            # Parse JSON fields
            description_features = item.description_features
            if isinstance(description_features, str):
                try:
                    description_features = json.loads(description_features)
                except:
                    description_features = []
            
            specifications = item.specifications
            if isinstance(specifications, str):
                try:
                    specifications = json.loads(specifications)
                except:
                    specifications = []
            
            print(f"📸 ITEM GALLERY DATA: {item.gallery}")
            print(f"📸 ITEM GALLERY TYPE: {type(item.gallery)}")
            print(f"📸 ITEM GALLERY LENGTH: {len(item.gallery) if item.gallery else 0}")
            
            # Create product
            product = Product.objects.create(
                vendor=vendor,
                product_name=item.itemName,
                sku=f"ITEM-{item.id}-{item.itemName[:8]}".upper(),
                brand=item.c_brand,
                category=item.c_category,
                subcategory=item.c_subCategory,
                subsubcategory=item.c_subSubCategory,
                product_type='variant' if item.variants.count() > 1 else 'simple',
                keywords=item.keywords or '',
                short_description=item.short_description or '',
                full_description=item.full_description or '',
                product_condition=item.product_condition or 'New',
                return_policy=item.return_policy or '',
                estimated_delivery_time=item.estimated_delivery_time or '',
                free_shipping=item.free_shipping,
                description_features=description_features or [],
                specifications=specifications or [],
                warranty_available=item.warranty_available,
                warranty_period=item.warranty_period,
                warranty_type=item.warranty_type,
                warranty_description=item.warranty_description,
                status='approved',
                main_image=item.main_image,
                thumbnail_image=item.thumbnail_image
            )
            
            print(f"✅ Product created: ID {product.id}")
            
            # 🔥 CRITICAL: SYNC GALLERY IMAGES - FIXED APPROACH
            if item.gallery and isinstance(item.gallery, list) and len(item.gallery) > 0:
                print(f"📸 Processing {len(item.gallery)} gallery images...")
                
                for idx, gallery_path in enumerate(item.gallery):
                    print(f"📸 Gallery image {idx + 1}: {gallery_path}")
                    
                    if not gallery_path:
                        print(f"⚠️ Empty gallery path at index {idx}")
                        continue
                    
                    try:
                        # 🔥 FIX: Build the full file system path
                        # gallery_path is like "items/gallery/15_20260404_064901_red_sari4.webp"
                        full_path = os.path.join(settings.MEDIA_ROOT, gallery_path)
                        print(f"📸 Full filesystem path: {full_path}")
                        
                        if os.path.exists(full_path):
                            print(f"✅ File found at: {full_path}")
                            
                            # Open the file and create ProductGallery
                            with open(full_path, 'rb') as f:
                                from django.core.files import File
                                django_file = File(f)
                                
                                gallery_obj = ProductGallery.objects.create(
                                    product=product,
                                    image=django_file
                                )
                                print(f"✅ Created gallery image {idx + 1} for product {product.id}: {gallery_obj.image.url}")
                        else:
                            print(f"❌ Gallery image file NOT FOUND: {full_path}")
                            
                            # Try alternative path using default_storage
                            if default_storage.exists(gallery_path):
                                print(f"✅ Found via default_storage: {gallery_path}")
                                file_content = default_storage.open(gallery_path, 'rb')
                                gallery_obj = ProductGallery.objects.create(
                                    product=product,
                                    image=ContentFile(file_content.read(), name=os.path.basename(gallery_path))
                                )
                                file_content.close()
                                print(f"✅ Created gallery image via storage: {gallery_obj.image.url}")
                            else:
                                print(f"❌ Gallery image not found anywhere")
                                
                    except Exception as e:
                        print(f"❌ Failed to copy gallery image {gallery_path}: {str(e)}")
                        import traceback
                        traceback.print_exc()
            else:
                print(f"📸 No gallery images to sync")
            
            # Create stock entries for each variant
            tax_rate = float(item.taxSlab.replace('%', '')) if item.taxSlab else 0
            
            for variant in item.variants.all():
                stock = ProductStock.objects.create(
                    product=product,
                    mrp=variant.mrp,
                    selling_price=variant.salesPrice,
                    tax=tax_rate,
                    stock_quantity=variant.current_stock or variant.opStock,
                    barcode=str(variant.barcode) if variant.barcode else '',
                    unit=item.unit or '',
                    weight='',
                    color=variant.color or '',
                    size=variant.size or '',
                    maximum_order_quantity=10,
                    final_price=variant.salesPrice,
                    variant_image=variant.variant_image, 
                    platform_charge_percent=platform_charge
                )
                stock.save()
            
            # Link product to item
            item.linked_product = product
            item.website_status = 'approved'
            item.save()
            
            final_gallery_count = product.gallery.count()
            print(f"🎉 Product {product.id} created with {final_gallery_count} gallery images")
            
            if final_gallery_count == 0 and item.gallery and len(item.gallery) > 0:
                print(f"⚠️ WARNING: Item had {len(item.gallery)} gallery images but none were copied to product!")
            
            return True, "Product created successfully", product.id
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Error syncing item: {str(e)}", None
    
    @staticmethod
    def update_product_from_item(item_id):
        """
        Update existing product when item is updated
        """
        import os  # ✅ Make sure os is imported here too
        from pos.models.items import items
        from ecommerce.models.product import Product, ProductStock, ProductGallery 
        from decimal import Decimal
        import json
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage
        
        try:
            item = items.objects.get(id=item_id)
            
            if not item.linked_product:
                return False, "No linked product found"
            
            product = item.linked_product
            
            # Parse JSON fields
            description_features = item.description_features
            if isinstance(description_features, str):
                try:
                    description_features = json.loads(description_features)
                except:
                    description_features = []
            
            specifications = item.specifications
            if isinstance(specifications, str):
                try:
                    specifications = json.loads(specifications)
                except:
                    specifications = []
            
            # Update product fields
            product.product_name = item.itemName
            product.brand = item.c_brand
            product.category = item.c_category
            product.subcategory = item.c_subCategory
            product.subsubcategory = item.c_subSubCategory
            product.keywords = item.keywords or ''
            product.short_description = item.short_description or ''
            product.full_description = item.full_description or ''
            product.product_condition = item.product_condition or 'New'
            product.return_policy = item.return_policy or ''
            product.estimated_delivery_time = item.estimated_delivery_time or ''
            product.free_shipping = item.free_shipping
            product.description_features = description_features or []
            product.specifications = specifications or []
            product.warranty_available = item.warranty_available
            product.warranty_period = item.warranty_period
            product.warranty_type = item.warranty_type
            product.warranty_description = item.warranty_description
            
            # Only update images if new ones are provided
            if item.main_image:
                product.main_image = item.main_image
            if item.thumbnail_image:
                product.thumbnail_image = item.thumbnail_image
            
            # Set status to pending for re-approval
            if product.status == 'approved':
                product.status = 'pending'
            
            product.save()
            
            # ✅ UPDATE GALLERY - Delete old and copy new
            product.gallery.all().delete()

            if item.gallery and isinstance(item.gallery, list) and len(item.gallery) > 0:
                print(f"📸 Updating {len(item.gallery)} gallery images...")
                
                for idx, gallery_path in enumerate(item.gallery):
                    if gallery_path:
                        try:
                            # Build full file system path
                            full_path = os.path.join(settings.MEDIA_ROOT, gallery_path)
                            print(f"📸 Full filesystem path: {full_path}")
                            
                            if os.path.exists(full_path):
                                with open(full_path, 'rb') as f:
                                    from django.core.files import File
                                    django_file = File(f)
                                    ProductGallery.objects.create(
                                        product=product,
                                        image=django_file
                                    )
                                    print(f"✅ Updated gallery image {idx + 1}")
                            else:
                                print(f"❌ Gallery image not found: {full_path}")
                        except Exception as e:
                            print(f"⚠️ Failed to copy gallery image {gallery_path}: {e}")

            # Update stocks
            product.stocks.all().delete()
            
            tax_rate = float(item.taxSlab.replace('%', '')) if item.taxSlab else 0
            platform_charge = item.c_category.platform_charge if item.c_category else Decimal('0.00')
            
            for variant in item.variants.all():
                stock = ProductStock.objects.create(
                    product=product,
                    mrp=variant.mrp,
                    selling_price=variant.salesPrice,
                    tax=tax_rate,
                    stock_quantity=variant.current_stock or variant.opStock,
                    barcode=str(variant.barcode) if variant.barcode else '',
                    unit=item.unit or '',
                    weight='',
                    color=variant.color or '',
                    size=variant.size or '',
                    maximum_order_quantity=10,
                    final_price=variant.salesPrice,
                    variant_image=variant.variant_image,
                    platform_charge_percent=platform_charge
                )
                stock.save()
            
            return True, "Product updated successfully", product.id
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Error updating product: {str(e)}", None
        
        
        