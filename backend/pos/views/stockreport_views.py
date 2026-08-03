# pos/views/stockreport_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Max
from decimal import Decimal
from django.utils import timezone
from datetime import datetime

from pos.models.items import itemvariants
from pos.models.purchaseentry import PurchaseItem
from pos.models.salesentry import SalesItem
from pos.models.purchasereturn import PurchaseReturnItem
from pos.models.salesreturn import SalesReturnItem
from pos.models.stock_transfer import StockTransferItem
from pos.models.stock_return import StockReturnItem
from pos.utils.pagination import StandardResultsSetPagination
from pos.models.b2b_transfer import B2BStockTransferItem
from pos.models.b2b_stock_return import B2BStockReturnItem
from pos.models.b2b_sales import B2BSaleItem
from django.db.models import Q
from pos.models.b2b_sales import B2BSaleItem

class StockReportAPIView(APIView):
    permission_classes = [IsAuthenticated]
 
    def get(self, request):

        user = request.user
        is_superadmin = user.role == 'superadmin'
 
        if is_superadmin:
            from pos.models.branch import Branch
 
            branch_id_param = request.GET.get('branch_id')
 
            if branch_id_param:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            else:
                try:
                    branch = Branch.objects.get(user=user)
                except Branch.DoesNotExist:
                    return Response({'error': 'Superadmin branch not found'}, status=400)
        else:
            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({'error': 'User branch not found'}, status=400)
 
        branch_id = branch.id
 
        variants_qs = list(
            itemvariants.objects.select_related(
                "item",
                "item__c_brand",
                "item__c_category",
                "item__c_subCategory",
                "item__c_subSubCategory",
                "item__unit",
            ).filter(
                item__branch_id=branch_id
            ).order_by('item__itemName', 'id')
        )
 
        if not variants_qs:
            paginator = StandardResultsSetPagination()
            paginated_result = paginator.paginate_queryset([], request)
            return paginator.get_paginated_response(paginated_result)
 
        variant_ids = [v.id for v in variants_qs]
        barcodes = [v.barcode for v in variants_qs if v.barcode]
 
        from ecommerce.models.order import OrderItem
 
        # ---------------------------------------------------------------
        #  BULK AGGREGATIONS (ek-ek query, saare variants ke liye ek saath)
        # ---------------------------------------------------------------
 
        # Total purchases per variant
        purchase_map = {
            row['variant_id']: row['total']
            for row in PurchaseItem.objects.filter(variant_id__in=variant_ids)
            .values('variant_id').annotate(total=Sum('quantity'))
        }
 
        # Total purchase returns per variant
        purchase_return_map = {
            row['variant_id']: row['total']
            for row in PurchaseReturnItem.objects.filter(variant_id__in=variant_ids)
            .values('variant_id').annotate(total=Sum('return_quantity'))
        }
 
        # Transfer received - to_variant FK se direct match (B2B jaisa hi pattern)
        transfer_received_map = {
            row['to_variant_id']: row['total']
            for row in StockTransferItem.objects.filter(
                to_variant_id__in=variant_ids,
                transfer__to_branch_id=branch_id,
                is_stock_updated=True,
            ).values('to_variant_id').annotate(total=Sum('quantity'))
        }

        # Transfer sent - only superadmin branch
        transfer_sent_map = {}
        if is_superadmin:
            transfer_sent_map = {
                row['from_variant_id']: row['total']
                for row in StockTransferItem.objects.filter(
                    from_variant_id__in=variant_ids,
                    transfer__from_branch_id=branch_id,
                    is_stock_updated=True,
                ).values('from_variant_id').annotate(total=Sum('quantity'))
            }
 
        # Stock return packaged - only normal branch
        stock_return_packaged_map = {}
        if not is_superadmin:
            stock_return_packaged_map = {
                row['branch_variant_id']: row['total']
                for row in StockReturnItem.objects.filter(
                    branch_variant_id__in=variant_ids,
                    return_request__branch_id=branch_id,
                    is_packaging_ready=True,
                ).values('branch_variant_id').annotate(total=Sum('quantity'))
            }
 
        # Stock return received - only superadmin
        stock_return_received_map = {}
        if is_superadmin:
            stock_return_received_map = {
                row['company_variant_id']: row['total']
                for row in StockReturnItem.objects.filter(
                    company_variant_id__in=variant_ids,
                    return_request__to_branch_id=branch_id,
                    is_returned_to_company=True,
                ).values('company_variant_id').annotate(total=Sum('quantity'))
            }

        # ✅ B2B stock received — to_variant direct match, koi branch check ki zaroorat nahi
        # (to_variant already destination-branch ka variant hai)
        b2b_received_map = {
            row['to_variant_id']: row['total']
            for row in B2BStockTransferItem.objects.filter(
                to_variant_id__in=variant_ids,
                transfer__to_branch_id=branch_id,
                is_received=True,
            ).values('to_variant_id').annotate(total=Sum('quantity'))
        }

        
        
        # B2B stock sent — from_variant direct match, packaging-ready ho chuki ho
        b2b_sent_map = {
            row['from_variant_id']: row['total']
            for row in B2BStockTransferItem.objects.filter(
                from_variant_id__in=variant_ids,
                transfer__from_branch_id=branch_id,
                is_packaged=True,
            ).values('from_variant_id').annotate(total=Sum('quantity'))
        }
        
        #  B2B return packaged - branch side deduction (bulk map)
        b2b_return_packaged_map = {}
        if not is_superadmin:
            b2b_return_packaged_map = {
                row['branch_variant_id']: row['total']
                for row in B2BStockReturnItem.objects.filter(
                    branch_variant_id__in=variant_ids,
                    return_request__branch_id=branch_id,
                    is_packaging_ready=True,
                ).values('branch_variant_id').annotate(total=Sum('quantity'))
            }

        #  B2B return received - superadmin side increase (bulk map)
        b2b_return_received_map = {}
        if is_superadmin:
            b2b_return_received_map = {
                row['company_variant_id']: row['total']
                for row in B2BStockReturnItem.objects.filter(
                    company_variant_id__in=variant_ids,
                    return_request__to_branch_id=branch_id,
                    is_returned_to_company=True,
                ).values('company_variant_id').annotate(total=Sum('quantity'))
            }
        
        b2bsale_sent_map = {}
        if is_superadmin:
            b2bsale_sent_map = {
                row['from_variant_id']: row['total']
                for row in B2BSaleItem.objects.filter(
                    from_variant_id__in=variant_ids,
                    sale__from_branch_id=branch_id,
                ).exclude(
                    Q(sale__status='cancelled') & Q(is_stock_updated=False)
                ).values('from_variant_id').annotate(total=Sum('quantity'))
            }

        
        # Total sales POS per variant
        sales_pos_map = {
            row['variant_id']: row['total']
            for row in SalesItem.objects.filter(variant_id__in=variant_ids)
            .values('variant_id').annotate(total=Sum('qty'))
        }
 
        # Total sales website (delivered) per variant
        sales_website_map = {
            row['product_stock_id']: row['total']
            for row in OrderItem.objects.filter(
                product_stock_id__in=variant_ids,
                item_status='delivered',
            ).values('product_stock_id').annotate(total=Sum('quantity'))
        }
 
        # Total sales returns per variant
        sales_return_map = {
            row['variant_id']: row['total']
            for row in SalesReturnItem.objects.filter(variant_id__in=variant_ids)
            .values('variant_id').annotate(total=Sum('return_quantity'))
        }
 
        # Last purchase price per variant (bulk, without per-row query)
        last_purchase_ids = list(
            PurchaseItem.objects.filter(variant_id__in=variant_ids)
            .values('variant_id').annotate(last_id=Max('id'))
            .values_list('last_id', flat=True)
        )
        last_price_map = {
            row['variant_id']: row['price']
            for row in PurchaseItem.objects.filter(id__in=last_purchase_ids)
            .values('variant_id', 'price')
        }
 
        # ---------------------------------------------------------------
        #  Ab sirf Python-side loop, DB hit nahi (sab dict lookup se)
        # ---------------------------------------------------------------
        result = []
        variants_to_update = []
 
        for variant in variants_qs:
            vid = variant.id
            barcode = variant.barcode
 
            opening_stock = Decimal(str(variant.opStock or 0))
            total_purchased = purchase_map.get(vid) or Decimal('0')
            total_purchase_returns = purchase_return_map.get(vid) or Decimal('0')
            total_transfer_received = transfer_received_map.get(vid) or Decimal('0')   # ✅ FIXED
            total_transfer_sent = transfer_sent_map.get(vid) or Decimal('0')
            total_stock_return_packaged = stock_return_packaged_map.get(vid) or Decimal('0')
            total_stock_return_received = stock_return_received_map.get(vid) or Decimal('0')
            total_b2b_received = b2b_received_map.get(vid) or Decimal('0')
            total_b2b_sent = b2b_sent_map.get(vid) or Decimal('0')
            total_b2b_return_packaged = b2b_return_packaged_map.get(vid) or Decimal('0')
            total_b2b_return_received = b2b_return_received_map.get(vid) or Decimal('0')
            total_sold_pos = sales_pos_map.get(vid) or Decimal('0')
            total_sold_website = sales_website_map.get(vid) or Decimal('0')
            total_sold = total_sold_pos + total_sold_website
            total_sales_returns = sales_return_map.get(vid) or Decimal('0')
            total_b2bsale_sent = b2bsale_sent_map.get(vid) or Decimal('0')

 
            calculated_stock = (
                opening_stock
                + total_purchased
                - total_purchase_returns
                + total_transfer_received
                - total_transfer_sent
                - total_stock_return_packaged
                + total_stock_return_received
                + total_b2b_received     
                - total_b2b_sent 
                - total_b2b_return_packaged  
                + total_b2b_return_received 
                - total_sold
                + total_sales_returns
                - total_b2bsale_sent

            )
 
            if calculated_stock < 0:
                calculated_stock = Decimal('0')
 
            db_stock = Decimal(str(variant.current_stock or 0))
            if db_stock != calculated_stock:
                variant.current_stock = float(calculated_stock) 
                variants_to_update.append(variant)
 
            last_price = last_price_map.get(vid)
            last_price = float(last_price) if last_price is not None else float(variant.purchasePrice or 0)
            
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
 
        # Ek hi bulk UPDATE query - N individual .save() ki jagah
        if variants_to_update:
            itemvariants.objects.bulk_update(variants_to_update, ['current_stock'], batch_size=500)
 
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

        #  Variant fetch - branch check ke saath
        try:
            variant = itemvariants.objects.get(
                id=variant_id,
                item__branch=branch
            )
        except itemvariants.DoesNotExist:
            return Response({"error": "Variant not found"}, status=404)
        
        barcode = variant.barcode

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

        #  Transfer Received - to_variant FK se direct match
        for st in StockTransferItem.objects.filter(
            to_variant=variant,
            transfer__to_branch=branch,
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

        #  STOCK RETURN PACKAGED - Branch stock deduction (ONLY FOR BRANCH)
        #  ADD THIS - NEW
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

        #  STOCK RETURN RECEIVED - Company stock increase (ONLY FOR SUPERADMIN)
        #  ADD THIS - NEW
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

        #  B2B Stock Transfer Received
        for bt in B2BStockTransferItem.objects.filter(
            to_variant_id=variant_id,
            transfer__to_branch=branch,
            is_received=True,
        ).select_related('transfer', 'transfer__from_branch').order_by('transfer__updated_at'):
            qty = Decimal(str(bt.quantity))
            running_stock += qty
            history.append({
                "date": bt.transfer.updated_at,
                "type": "B2B Transfer (Received)",
                "partyName": f"From: {bt.transfer.from_branch.branch_name}",
                "qty": float(qty),
                "billNo": bt.transfer.transfer_no,
                "billAmount": float(bt.rate * bt.quantity),
                "currentStock": float(running_stock),
            })

        #  B2B Stock Transfer Sent (packaging ready)
        for bt in B2BStockTransferItem.objects.filter(
            from_variant_id=variant_id,
            transfer__from_branch=branch,
            is_packaged=True,
        ).select_related('transfer', 'transfer__to_branch').order_by('transfer__updated_at'):
            qty = -Decimal(str(bt.quantity))
            running_stock += qty
            history.append({
                "date": bt.transfer.updated_at,
                "type": "B2B Transfer (Sent)",
                "partyName": f"To: {bt.transfer.to_branch.branch_name}",
                "qty": float(qty),
                "billNo": bt.transfer.transfer_no,
                "billAmount": float(bt.rate * bt.quantity),
                "currentStock": float(running_stock),
            })
        
        
        #  NEW — B2B STOCK RETURN PACKAGED (Branch side stock deduction)
        if not is_superadmin:
            for br in B2BStockReturnItem.objects.filter(
                branch_variant_id=variant_id,
                return_request__branch=branch,
                is_packaging_ready=True,
            ).select_related('return_request', 'return_request__to_branch').order_by('return_request__updated_at'):
                qty = -Decimal(str(br.quantity))
                running_stock += qty
                history.append({
                    "date": br.return_request.updated_at,
                    "type": "B2B Return (Sent)",
                    "partyName": f"To: {br.return_request.to_branch.branch_name}",
                    "qty": float(qty),
                    "billNo": br.return_request.return_no,
                    "billAmount": float(br.quantity * br.rate),
                    "currentStock": float(running_stock),
                })

        #  NEW — B2B STOCK RETURN RECEIVED (Superadmin/Company side stock increase)
        if is_superadmin:
            for br in B2BStockReturnItem.objects.filter(
                company_variant_id=variant_id,
                return_request__to_branch=branch,
                is_returned_to_company=True,
            ).select_related('return_request', 'return_request__branch').order_by('return_request__updated_at'):
                qty = Decimal(str(br.quantity))
                running_stock += qty
                history.append({
                    "date": br.return_request.updated_at,
                    "type": "B2B Return (Received)",
                    "partyName": f"From: {br.return_request.branch.branch_name}",
                    "qty": float(qty),
                    "billNo": br.return_request.return_no,
                    "billAmount": float(br.quantity * br.rate),
                    "currentStock": float(running_stock),
                })
                
                #  NEW: B2B SALE SENT - Superadmin branch se stock deduct (creation pe hi ho chuka hai)
        if is_superadmin:
            for b2b_item in B2BSaleItem.objects.filter(
                from_variant_id=variant_id,
                sale__from_branch=branch,
            ).exclude(
                Q(sale__status='cancelled') & Q(is_stock_updated=False)
            ).select_related('sale', 'sale__to_branch').order_by('sale__created_at'):
                qty = -Decimal(str(b2b_item.quantity))
                running_stock += qty
                history.append({
                    "date": b2b_item.sale.created_at,
                    "type": "B2B Sale (Sent)",
                    "partyName": f"To: {b2b_item.sale.to_branch.branch_name}",
                    "qty": float(qty),
                    "billNo": b2b_item.sale.sale_no,
                    "billAmount": float(b2b_item.rate * b2b_item.quantity),
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