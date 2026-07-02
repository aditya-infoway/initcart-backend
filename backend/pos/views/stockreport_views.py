# pos/views/stockreport_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from decimal import Decimal
from django.utils import timezone
from datetime import datetime

from pos.models.items import itemvariants
from pos.models.purchaseentry import PurchaseItem
from pos.models.salesentry import SalesItem
from pos.models.purchasereturn import PurchaseReturnItem
from pos.models.salesreturn import SalesReturnItem
from pos.models.stock_transfer import StockTransferItem
from pos.models.stock_return import StockReturnItem  # ✅ ADD THIS IMPORT
from pos.utils.pagination import StandardResultsSetPagination


class StockReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            from pos.models.branch import Branch
            
            # ✅ Branch filter — query param se
            branch_id_param = request.GET.get('branch_id')
            
            if branch_id_param:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            else:
                # Default: superadmin ki apni branch
                try:
                    branch = Branch.objects.get(user=user)
                except Branch.DoesNotExist:
                    return Response({'error': 'Superadmin branch not found'}, status=400)
        else:
            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({'error': 'User branch not found'}, status=400)

        branch_id = branch.id

        # ✅ Is branch ke SAARE variants
        variants_qs = itemvariants.objects.select_related(
            "item",
            "item__c_brand",
            "item__c_category",
            "item__c_subCategory",
            "item__c_subSubCategory",
            "item__unit"
        ).filter(
            item__branch_id=branch_id
        ).order_by('item__itemName', 'id')

        from ecommerce.models.order import OrderItem

        result = []

        for variant in variants_qs:
            variant_id = variant.id

            # Opening stock
            opening_stock = Decimal(str(variant.opStock or 0))

            # Total purchases
            total_purchased = PurchaseItem.objects.filter(
                variant_id=variant_id
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # Total purchase returns
            total_purchase_returns = PurchaseReturnItem.objects.filter(
                variant_id=variant_id
            ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')

            # ✅ Transfer received - barcode se match
            barcode = variant.barcode
            total_transfer_received = Decimal('0')
            if barcode:
                total_transfer_received = StockTransferItem.objects.filter(
                    from_variant__barcode=barcode,
                    transfer__to_branch_id=branch_id,
                    transfer__status='completed',
                    is_stock_updated=True
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # ✅ Transfer sent - sirf superadmin branch se gaya hua
            total_transfer_sent = Decimal('0')
            if is_superadmin:
                total_transfer_sent = StockTransferItem.objects.filter(
                    from_variant_id=variant_id,
                    transfer__from_branch_id=branch_id,
                    transfer__status='completed',
                    is_stock_updated=True
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # ✅ STOCK RETURN PACKAGED - Branch stock deduction (ONLY FOR BRANCH)
            # ✅ ADD THIS - NEW
            total_stock_return_packaged = Decimal('0')
            if not is_superadmin:
                # Stock return packaging means stock decreased from branch
                total_stock_return_packaged = StockReturnItem.objects.filter(
                    branch_variant_id=variant_id,
                    return_request__branch_id=branch_id,
                    is_packaging_ready=True,
                    # is_returned_to_company=False
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # ✅ STOCK RETURN RECEIVED - Company stock increase (ONLY FOR SUPERADMIN)
            # ✅ ADD THIS - NEW
            total_stock_return_received = Decimal('0')
            if is_superadmin:
                # Stock return received means stock increased in company
                total_stock_return_received = StockReturnItem.objects.filter(
                    company_variant_id=variant_id,
                    return_request__to_branch_id=branch_id,
                    is_returned_to_company=True
                ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            # Total sales POS
            total_sold_pos = SalesItem.objects.filter(
                variant_id=variant_id
            ).aggregate(total=Sum('qty'))['total'] or Decimal('0')

            # Total sales Website - only delivered
            total_sold_website = OrderItem.objects.filter(
                product_stock_id=variant_id,
                item_status='delivered'
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')

            total_sold = total_sold_pos + total_sold_website

            # Total sales returns
            total_sales_returns = SalesReturnItem.objects.filter(
                variant_id=variant_id
            ).aggregate(total=Sum('return_quantity'))['total'] or Decimal('0')

            # ✅ Final stock calculation - ADDED stock return fields
            calculated_stock = (
                opening_stock
                + total_purchased
                - total_purchase_returns
                + total_transfer_received
                - total_transfer_sent
                - total_stock_return_packaged      # ✅ ADD THIS - Branch deduction
                + total_stock_return_received       # ✅ ADD THIS - Company increase
                - total_sold
                + total_sales_returns
            )

            # Stock negative nahi honi chahiye
            if calculated_stock < 0:
                calculated_stock = Decimal('0')

            # DB update if mismatch
            try:
                db_stock = Decimal(str(variant.current_stock or 0))
                if db_stock != calculated_stock:
                    variant.current_stock = float(calculated_stock)
                    variant.save(update_fields=['current_stock'])
            except Exception:
                pass

            # Last purchase price
            last_purchase = PurchaseItem.objects.filter(
                variant_id=variant_id
            ).order_by('-id').first()
            last_price = float(last_purchase.price) if last_purchase else float(variant.purchasePrice or 0)

            result.append({
                'variantId': variant.id,
                'id': variant.item.id,
                'itemName': variant.item.itemName,
                'hsnCode': variant.item.hsnCode or '',
                'unit': variant.item.unit.name if variant.item.unit else 'Piece',
                'brand': {
                    'id': variant.item.c_brand.id if variant.item.c_brand else None,
                    'name': variant.item.c_brand.brand_name if variant.item.c_brand else (variant.item.brand or None),
                },
                'category': {
                    'id': variant.item.c_category.id if variant.item.c_category else None,
                    'name': variant.item.c_category.name if variant.item.c_category else (variant.item.category or None),
                },
                'subCategory': {
                    'id': variant.item.c_subCategory.id if variant.item.c_subCategory else None,
                    'name': variant.item.c_subCategory.name if variant.item.c_subCategory else (variant.item.subCategory or None),
                },
                'subSubCategory': {
                    'id': variant.item.c_subSubCategory.id if variant.item.c_subSubCategory else None,
                    'name': variant.item.c_subSubCategory.name if variant.item.c_subSubCategory else (variant.item.subSubCategory or None),
                },
                'size': variant.size or '',
                'color': variant.color or '',
                'srno': variant.srno or '',
                'warrantydate': variant.warrantydate.strftime('%Y-%m-%d') if variant.warrantydate else '',
                'purchasePrice': last_price,
                'salesPrice': float(variant.salesPrice or 0),
                'current_stock': float(calculated_stock),
                'created_by_superadmin': variant.item.created_by_superadmin,
            })

        # ✅ Pagination
        paginator = StandardResultsSetPagination()
        paginated_result = paginator.paginate_queryset(result, request)
        return paginator.get_paginated_response(paginated_result)


class StockHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, item_id):
        from ecommerce.models.order import OrderItem

        variant_id = request.GET.get("variant_id")
        if not variant_id:
            return Response({"error": "variant_id is required"}, status=400)

        variant_id = int(variant_id)

        user = request.user
        is_superadmin = user.role == 'superadmin'

        # ✅ Branch fetch
        if is_superadmin:
            from pos.models.branch import Branch
            try:
                branch = Branch.objects.get(user=user)
            except Branch.DoesNotExist:
                return Response({"error": "Branch not found"}, status=400)
        else:
            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({"error": "Branch not found"}, status=400)

        # ✅ Variant fetch - branch check ke saath
        try:
            variant = itemvariants.objects.get(
                id=variant_id,
                item__branch=branch
            )
        except itemvariants.DoesNotExist:
            return Response({"error": "Variant not found"}, status=404)

        history = []

        # Opening stock
        opening_stock = Decimal(str(variant.opStock or 0))
        running_stock = opening_stock

        history.append({
            "date": None,
            "type": "Opening",
            "partyName": "-",
            "qty": float(opening_stock),
            "billNo": "-",
            "billAmount": 0,
            "currentStock": float(running_stock),
        })

        # Purchases
        for p in PurchaseItem.objects.filter(
            variant_id=variant_id
        ).select_related('purchase', 'purchase__partyName').order_by('created_at'):
            qty = Decimal(str(p.quantity))
            running_stock += qty
            history.append({
                "date": p.created_at,
                "type": "Purchase",
                "partyName": p.purchase.partyName.account_name if p.purchase.partyName else "",
                "qty": float(qty),
                "billNo": p.purchase.billNo,
                "billAmount": float(p.netValue),
                "currentStock": float(running_stock),
            })

        # Purchase Returns
        for pr in PurchaseReturnItem.objects.filter(
            variant_id=variant_id
        ).select_related('purchase_return', 'purchase_return__party').order_by('created_at'):
            qty = -Decimal(str(pr.return_quantity))
            running_stock += qty
            history.append({
                "date": pr.created_at,
                "type": "Purchase Return",
                "partyName": pr.purchase_return.party.account_name if pr.purchase_return.party else "",
                "qty": float(qty),
                "billNo": pr.purchase_return.return_no,
                "billAmount": float(pr.net_amount),
                "currentStock": float(running_stock),
            })

        # ✅ Transfer Received - barcode se match
        barcode = variant.barcode
        if barcode:
            for st in StockTransferItem.objects.filter(
                from_variant__barcode=barcode,
                transfer__to_branch=branch,
                transfer__status='completed',
                is_stock_updated=True
            ).select_related('transfer', 'transfer__from_branch').order_by('transfer__updated_at'):
                qty = Decimal(str(st.quantity))
                running_stock += qty
                history.append({
                    "date": st.transfer.updated_at,
                    "type": "Stock Transfer (Received)",
                    "partyName": f"From: {st.transfer.from_branch.branch_name}",
                    "qty": float(qty),
                    "billNo": st.transfer.transfer_no,
                    "billAmount": float(st.rate * st.quantity),
                    "currentStock": float(running_stock),
                })

        # Transfer Sent - only superadmin
        if is_superadmin:
            for st in StockTransferItem.objects.filter(
                from_variant_id=variant_id,
                transfer__from_branch=branch,
                transfer__status='completed',
                is_stock_updated=True
            ).select_related('transfer', 'transfer__to_branch').order_by('transfer__updated_at'):
                qty = -Decimal(str(st.quantity))
                running_stock += qty
                history.append({
                    "date": st.transfer.updated_at,
                    "type": "Stock Transfer (Sent)",
                    "partyName": f"To: {st.transfer.to_branch.branch_name}",
                    "qty": float(qty),
                    "billNo": st.transfer.transfer_no,
                    "billAmount": float(st.rate * st.quantity),
                    "currentStock": float(running_stock),
                })

        # ✅ STOCK RETURN PACKAGED - Branch stock deduction (ONLY FOR BRANCH)
        # ✅ ADD THIS - NEW
        if not is_superadmin:
            for sr in StockReturnItem.objects.filter(
                branch_variant_id=variant_id,
                return_request__branch=branch,
                is_packaging_ready=True,
                # is_returned_to_company=False
            ).select_related('return_request', 'return_request__to_branch').order_by('return_request__updated_at'):
                qty = -Decimal(str(sr.quantity))
                running_stock += qty
                history.append({
                    "date": sr.return_request.updated_at,
                    "type": "Stock Return (Sent)",
                    "partyName": f"To: {sr.return_request.to_branch.branch_name}",
                    "qty": float(qty),
                    "billNo": sr.return_request.return_no,
                    "billAmount": float(sr.quantity * sr.rate),
                    "currentStock": float(running_stock),
                })

        # ✅ STOCK RETURN RECEIVED - Company stock increase (ONLY FOR SUPERADMIN)
        # ✅ ADD THIS - NEW
        if is_superadmin:
            for sr in StockReturnItem.objects.filter(
                company_variant_id=variant_id,
                return_request__to_branch=branch,
                is_returned_to_company=True
            ).select_related('return_request', 'return_request__branch').order_by('return_request__updated_at'):
                qty = Decimal(str(sr.quantity))
                running_stock += qty
                history.append({
                    "date": sr.return_request.updated_at,
                    "type": "Stock Return (Received)",
                    "partyName": f"From: {sr.return_request.branch.branch_name}",
                    "qty": float(qty),
                    "billNo": sr.return_request.return_no,
                    "billAmount": float(sr.quantity * sr.rate),
                    "currentStock": float(running_stock),
                })

        # Sales POS
        for s in SalesItem.objects.filter(
            variant_id=variant_id
        ).select_related('sales', 'sales__customer').order_by('created_at'):
            qty = -Decimal(str(s.qty))
            running_stock += qty
            history.append({
                "date": s.created_at,
                "type": "Sale (POS)",
                "partyName": s.sales.customer.account_name if s.sales.customer else "",
                "qty": float(qty),
                "billNo": s.sales.bill_no,
                "billAmount": float(s.net_amount),
                "currentStock": float(running_stock),
            })

        # Sales Website
        for ws in OrderItem.objects.filter(
            product_stock_id=variant_id,
            item_status='delivered'
        ).select_related('order').order_by('created_at'):
            qty = -Decimal(str(ws.quantity))
            running_stock += qty
            history.append({
                "date": ws.created_at,
                "type": "Sale (Website)",
                "partyName": ws.order.billing_name if ws.order else "",
                "qty": float(qty),
                "billNo": ws.order.order_number if ws.order else "",
                "billAmount": float(ws.total_price),
                "currentStock": float(running_stock),
            })

        # Sales Returns
        for sr in SalesReturnItem.objects.filter(
            variant_id=variant_id
        ).select_related('sales_return', 'sales_return__customer').order_by('created_at'):
            qty = Decimal(str(sr.return_quantity))
            running_stock += qty
            history.append({
                "date": sr.created_at,
                "type": "Sales Return",
                "partyName": sr.sales_return.customer.account_name if sr.sales_return.customer else "",
                "qty": float(qty),
                "billNo": sr.sales_return.return_no,
                "billAmount": float(sr.net_amount),
                "currentStock": float(running_stock),
            })

        # Sort by date
        def safe_date(d):
            if d is None:
                return timezone.make_aware(datetime.min)
            return timezone.make_aware(d) if timezone.is_naive(d) else d

        history.sort(key=lambda x: safe_date(x["date"]))

        # Sort ke baad running stock recalculate karo
        running_stock = Decimal('0')
        for row in history:
            qty = Decimal(str(row["qty"]))
            if row["type"] == "Opening":
                running_stock = qty
            else:
                running_stock += qty
            row["currentStock"] = float(running_stock)

        # DB update
        try:
            if Decimal(str(variant.current_stock or 0)) != running_stock:
                variant.current_stock = float(running_stock)
                variant.save(update_fields=['current_stock'])
        except Exception:
            pass

        return Response(history)