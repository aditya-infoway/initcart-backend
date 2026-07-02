# pos/views/item_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework import status

from pos.models.items import items, itemvariants
from ecommerce.models.category import Category, SubSubCategory, SubCategory
from ecommerce.models.vendor import Brand
from django.db.models import Q
from pos.models.branch import Branch
from pos.serializers.item_serializers import (
    itemSerializers,
    ItemWithVariantsSerializer,
    VariantSerializer,
    CategorySerializer,
    SubCategorySerializer,
    SubSubCategorySerializer,
    BrandSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination 


# ------------------ Item CRUD ------------------
class ItemCreate(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        user = request.user 
        is_superadmin = user.role == 'superadmin'

        # Normal branch sirf manual bana sakti hai
        entry_type = request.data.get('entry_type', 'manual')
        if not is_superadmin and entry_type == 'company':
            return Response(
                {"success": False, "message": "Normal branches can only create manual items."},
                status=status.HTTP_403_FORBIDDEN
            )

        if is_superadmin:
            # superadmin ke liye branch unki apni hogi
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"success": False, "message": "Superadmin branch not found."}, status=400)
        else:
            branch = getattr(user, "branch", None)
            if not branch:
                return Response({"success": False, "message": "User has no branch"}, status=400)

        serializer = itemSerializers(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        item = serializer.save(
            branch=branch,
            created_by_superadmin=is_superadmin
        )

        return Response({"success": True, "item_id": item.id}, status=status.HTTP_201_CREATED)

    def get(self, request):
        try:
            branch = request.user.branch
        except Exception:
            return Response({"success": False, "message": "User has no branch associated"}, status=400)
        return Response({"success": True, "branch_id": branch.id, "branch_type": branch.branch_type})



class Itemvariantview(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        branch = getattr(request.user, "branch", None)
        item_id = request.data.get("item")

        if not branch:
            return Response({"success": False, "message": "No branch"}, status=400)

        try:
            item = items.objects.get(id=item_id, branch=branch)
        except items.DoesNotExist:
            return Response({"success": False, "message": "Invalid item"}, status=400)

        serializer = VariantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(item=item)
            return Response({"success": True, "variant": serializer.data}, status=201)

        return Response(serializer.errors, status=400)


# ------------------ Item Delete (FIXED) ------------------
class Itemdelete(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def delete(self, request, id):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
                item = items.objects.get(id=id, branch=branch)
            except (Branch.DoesNotExist, items.DoesNotExist):
                return Response({"error": "Item not found"}, status=404)
        else:
            branch = getattr(user, "branch", None)
            # Normal branch sirf apne manual items delete kar sakti hai
            try:
                item = items.objects.get(id=id, branch=branch, created_by_superadmin=False)
            except items.DoesNotExist:
                return Response({"error": "Item not found or permission denied"}, status=404)

        itemvariants.objects.filter(item=item).delete()
        item.delete()
        return Response({"message": "Item deleted successfully"})


class Itemupdate(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def put(self, request, id):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
                item = items.objects.get(id=id, branch=branch)
            except (Branch.DoesNotExist, items.DoesNotExist):
                return Response({"error": "Item not found"}, status=404)
        else:
            branch = getattr(user, "branch", None)
            # Normal branch sirf apne manual items edit kar sakti hai
            try:
                item = items.objects.get(id=id, branch=branch, created_by_superadmin=False)
            except items.DoesNotExist:
                return Response({"error": "Item not found or permission denied"}, status=404)

        serializer = itemSerializers(
            item, data=request.data,
            context={"request": request, "is_update": True, "item_id": item.id}
        )
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "message": "Item updated successfully"})
        return Response(serializer.errors, status=400)

# ------------------ Branch Type Endpoint ------------------
class UserBranchTypeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        if user.role == 'superadmin':
            try:
                branch = Branch.objects.get(user=user)
                return Response({"branch_type": branch.branch_type})
            except Branch.DoesNotExist:
                return Response({"error": "Superadmin branch not found"}, status=400)
        try:
            branch = user.branch
        except Branch.DoesNotExist:
            return Response({"error": "User has no branch"}, status=400)
        return Response({"branch_type": branch.branch_type})


# ------------------ Branch Field Config ------------------
class BranchFieldConfig(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        data = {
            "Fashion": [
                {"key": "size", "label": "Size", "type": "text"},
                {"key": "color", "label": "Color", "type": "text"},
            ],
            "Mart": [
                {"key": "size", "label": "Size", "type": "text"},
            ],
            "Electronics": [
                {"key": "size", "label": "Size", "type": "text"},
                {"key": "color", "label": "Color", "type": "text"},
                {"key": "SRno", "label": "SR No.", "type": "text"},
                {"key": "warrantydate", "label": "Warranty Date", "type": "date"},
            ],
        }
        return Response(data)
        
# ================= ITEM LIST (WITH PAGINATION) =================

# pos/views/item_views.py - Update the Itemview class

from django.db.models import Q

class Itemview(APIView):
    """
    Item list - tab support ke saath:
    - tab=company: sirf company items
    - tab=manual: sirf manual items  
    - tab=all (default): sab items
    
    Normal branch ke liye:
    - superadmin ke created items bhi dikhenge (read-only)
    - apne manual items bhi dikhenge
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        # Tab filter
        tab = request.GET.get('tab', 'all')  # company | manual | all | superadmin_items | my_items
        search_term = request.GET.get('search', '').strip()
        category_filter = request.GET.get('category', '').strip()
        brand_filter = request.GET.get('brand', '').strip()
        group_filter = request.GET.get('group', '').strip()
        entry_type_filter = request.GET.get('entry_type', '').strip()

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"success": False, "message": "Superadmin branch not found."}, status=400)

            # Superadmin apne saare items dekh sakta hai
            qs = items.objects.filter(branch=branch).select_related(
                "c_brand", "c_category", "c_subCategory", "c_subSubCategory", "group", "unit"
            )

            # Tab filtering
            if tab == 'company':
                qs = qs.filter(entry_type='company')
            elif tab == 'manual':
                qs = qs.filter(entry_type='manual')
            # 'all' = kuch filter nahi

        else:
            branch = getattr(user, "branch", None)
            if not branch:
                return Response({"success": False, "message": "User has no branch"}, status=400)

            if tab == 'superadmin_items':
                # ✅ Sirf wo superadmin items jo IS branch mein transfer ho chuki hain
                qs = items.objects.filter(
                    branch=branch,
                    created_by_superadmin=True
                ).select_related("c_brand", "c_category", "c_subCategory", "c_subSubCategory", "group", "unit")

            elif tab == 'my_items':
                qs = items.objects.filter(
                    branch=branch,
                    created_by_superadmin=False
                ).select_related("c_brand", "c_category", "c_subCategory", "c_subSubCategory", "group", "unit")

            else:  # all
                # ✅ Sirf is branch ki items — superadmin wali bhi, apni bhi
                qs = items.objects.filter(
                    branch=branch  # ← yahi tha missing, pehle created_by_superadmin=True sab branches se aa raha tha
                ).select_related("c_brand", "c_category", "c_subCategory", "c_subSubCategory", "group", "unit")
        # Search
        if search_term:
            qs = qs.filter(
                Q(itemName__icontains=search_term) |
                Q(hsnCode__icontains=search_term) |
                Q(c_brand__brand_name__icontains=search_term) |
                Q(c_category__name__icontains=search_term) |
                Q(group__name__icontains=search_term)
            )

        # Filters
        if category_filter and category_filter != "All":
            if category_filter.isdigit():
                qs = qs.filter(c_category_id=int(category_filter))

        if brand_filter and brand_filter != "All":
            if brand_filter.isdigit():
                qs = qs.filter(c_brand_id=int(brand_filter))

        if group_filter and group_filter != "All":
            if group_filter.isdigit():
                qs = qs.filter(group_id=int(group_filter))

        if entry_type_filter and entry_type_filter != "All":
            qs = qs.filter(entry_type=entry_type_filter)

        qs = qs.order_by('-id')

        paginator = StandardResultsSetPagination()
        paginated_items = paginator.paginate_queryset(qs, request)
        serializer = ItemWithVariantsSerializer(paginated_items, many=True, context={"request": request, "branch": branch if not is_superadmin else None})

        return paginator.get_paginated_response({
            "success": True,
            "branch_type": branch.branch_type,
            "items": serializer.data
        })

# ---------------- FILTERS ----------------

class ItemFilterOptionsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"success": False, "message": "Branch not found"}, status=400)
            item_qs = items.objects.filter(branch=branch)
        else:
            branch = getattr(user, "branch", None)
            if not branch:
                return Response({"success": False, "message": "User has no branch"}, status=400)
            # Normal branch ke liye superadmin + apne items
            item_qs = items.objects.filter(
                Q(created_by_superadmin=True) | Q(branch=branch)
            )

        categories = Category.objects.filter(
            id__in=item_qs.filter(c_category__isnull=False).values_list('c_category', flat=True).distinct()
        )
        brands = Brand.objects.filter(
            id__in=item_qs.filter(c_brand__isnull=False).values_list('c_brand', flat=True).distinct()
        )
        from pos.models.group_unit import ItemGroup
        groups = ItemGroup.objects.filter(
            id__in=item_qs.filter(group__isnull=False).values_list('group', flat=True).distinct()
        )
        entry_types = item_qs.values_list('entry_type', flat=True).distinct()

        return Response({
            "success": True,
            "categories": [{"id": c.id, "name": c.name} for c in categories],
            "brands": [{"id": b.id, "name": b.brand_name} for b in brands],
            "groups": [{"id": g.id, "name": g.name} for g in groups],
            "entry_types": [{"value": e, "label": e.capitalize()} for e in entry_types if e]
        })
# ---------------- VARIANTS ----------------
class Itemvariantview(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        item_id = request.GET.get("item")

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"success": False, "variants": []}, status=400)
            qs = itemvariants.objects.filter(item__branch=branch)
        else:
            branch = getattr(user, "branch", None)
            if not branch:
                return Response({"success": False, "variants": []}, status=400)
            qs = itemvariants.objects.filter(item__branch=branch)

        if item_id:
            qs = qs.filter(item__id=item_id)

        serializer = VariantSerializer(qs, many=True)
        return Response({"success": True, "variants": serializer.data})

    def post(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        item_id = request.data.get("item")

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"success": False, "message": "No branch"}, status=400)
        else:
            branch = getattr(user, "branch", None)
            if not branch:
                return Response({"success": False, "message": "No branch"}, status=400)

        try:
            item = items.objects.get(id=item_id, branch=branch)
        except items.DoesNotExist:
            return Response({"success": False, "message": "Invalid item"}, status=400)

        serializer = VariantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(item=item)
            return Response({"success": True, "variant": serializer.data}, status=201)
        return Response(serializer.errors, status=400)

class CheckBranchBarcodeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        barcode = request.GET.get("barcode", "").strip()
        exclude_variant = request.GET.get("exclude_variant", None)

        if not barcode:
            return Response({"exists": False, "message": "No barcode provided"})

        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"exists": False, "message": "No branch associated"})
        else:
            branch = getattr(user, "branch", None)
            if not branch:
                return Response({"exists": False, "message": "No branch associated"})

        qs = itemvariants.objects.filter(barcode=barcode, item__branch=branch)
        if exclude_variant:
            try:
                qs = qs.exclude(id=int(exclude_variant))
            except (ValueError, TypeError):
                pass

        exists = qs.exists()
        return Response({
            "exists": exists,
            "barcode": barcode,
            "message": "Barcode already exists in this branch" if exists else "Barcode is available"
        })

class Itemvariantdelete(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            variant = itemvariants.objects.get(pk=pk)
            user = request.user
            is_superadmin = user.role == 'superadmin'

            if is_superadmin:
                branch = Branch.objects.get(user=user)
                if variant.item.branch != branch:
                    return Response({"error": "Unauthorized"}, status=403)
            else:
                if variant.item.branch != request.user.branch:
                    return Response({"error": "Unauthorized"}, status=403)

            variant.delete()
            return Response({"success": True})
        except itemvariants.DoesNotExist:
            return Response({"error": "Not found"}, status=404)


# ------------------ Category & SubCategory APIs ------------------

class CategoryListAPI(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        serializer = CategorySerializer(Category.objects.all(), many=True)
        return Response(serializer.data)


class SubCategoryListAPI(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        category_param = request.GET.get('category')
        if category_param and category_param.isdigit():
            qs = SubCategory.objects.filter(category_id=int(category_param))
        elif category_param:
            qs = SubCategory.objects.none()
        else:
            qs = SubCategory.objects.all()
        return Response(SubCategorySerializer(qs, many=True).data)


class SubSubCategoryListAPI(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        subcategory_param = request.GET.get("subcategory")
        if subcategory_param and subcategory_param.isdigit():
            qs = SubSubCategory.objects.filter(subcategory_id=int(subcategory_param))
        elif subcategory_param:
            qs = SubSubCategory.objects.none()
        else:
            qs = SubSubCategory.objects.all()
        return Response(SubSubCategorySerializer(qs, many=True).data)


class BrandListAPI(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        category_param = request.GET.get("category")
        qs = Brand.objects.all()
        if category_param and category_param.isdigit():
            qs = qs.filter(category_id=int(category_param))
        return Response(BrandSerializer(qs, many=True).data)



class ItemDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, pk):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            branch = Branch.objects.get(user=user)
            try:
                item = items.objects.get(id=pk, branch=branch)
            except items.DoesNotExist:
                return Response({"error": "Item not found"}, status=404)
        else:
            branch = getattr(user, "branch", None)
            try:
                item = items.objects.get(
                    Q(id=pk, created_by_superadmin=True) |
                    Q(id=pk, branch=branch)
                )
            except items.DoesNotExist:
                return Response({"error": "Item not found"}, status=404)

        serializer = itemSerializers(item, context={"request": request})
        return Response(serializer.data)


class ItemWithVariantsDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, pk):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            try:
                branch = Branch.objects.get(user=user)
                item = items.objects.get(id=pk, branch=branch)
            except (Branch.DoesNotExist, items.DoesNotExist):
                return Response({"error": "Item not found"}, status=404)
        else:
            branch = getattr(user, "branch", None)
            try:
                item = items.objects.get(
                    Q(id=pk, created_by_superadmin=True) |
                    Q(id=pk, branch=branch, created_by_superadmin=False)
                )
            except items.DoesNotExist:
                return Response({"error": "Item not found"}, status=404)

        item_serializer = ItemWithVariantsSerializer(item, context={"request": request})
        variants = itemvariants.objects.filter(item=item)
        variant_serializer = VariantSerializer(variants, many=True)

        item_data = dict(item_serializer.data)
        item_data['manual_brand'] = item.brand
        item_data['manual_category'] = item.category
        item_data['manual_subCategory'] = item.subCategory
        item_data['manual_subSubCategory'] = item.subSubCategory
        item_data['website_display'] = item.website_display
        item_data['entry_type'] = item.entry_type
        item_data['created_by_superadmin'] = item.created_by_superadmin

        return Response({
            "success": True,
            "item": item_data,
            "variants": variant_serializer.data
        })       
        
    