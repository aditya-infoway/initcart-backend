# pos/views/b2b_stock_return_views.py
"""
✅ COMPLETELY SEPARATE — B2B Stock Return views.
Existing pos/views/stock_return_views.py ko haath nahi lagaya — wo purana
flow (seedha company Stock Transfer se return) waisa hi chalega.

Yeh module sirf un items ke return ke liye hai jo kisi branch ko B2B
(branch-to-branch) transfer se mili thi.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django.db import transaction
from django.db.models import Q, Sum as SumModel
from django.contrib.auth import get_user_model

from pos.models.b2b_stock_return import B2BStockReturn, B2BStockReturnItem, B2BReturnSequence, get_financial_year
from pos.models.b2b_transfer import B2BStockTransfer, B2BStockTransferItem
from pos.models.branch import Branch
from pos.models.items import itemvariants as ItemVariants
from pos.serializers.b2b_stock_return_serializers import (
    B2BStockReturnListSerializer,
    B2BStockReturnDetailSerializer,
    B2BReturnItemStatusSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination
from pos.utils.gst_calc import calculate_gst_split
from pos.utils.transfer_chain import build_transfer_chain

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee, IsSuperAdminOrPagePermittedEmployee


User = get_user_model()


# ════════════════════════════════════════════════════════════
# Helper function — company branch fetch
# ════════════════════════════════════════════════════════════

def _get_company_branch():
    superadmin_user = User.objects.filter(role='superadmin').first()
    if not superadmin_user:
        return None
    return Branch.objects.filter(user=superadmin_user).first()


# ════════════════════════════════════════════════════════════
# BRANCH: Eligible B2B-received items for return
# ════════════════════════════════════════════════════════════
class EligibleB2BItemsForReturnView(APIView):
    """
    Sirf woh items jo is branch ko KISI B2B TRANSFER se mile the
    (is_received=True) aur abhi tak poori tarah return nahi hue.
    Har item ke saath uska pura transfer_chain milta hai — superadmin
    tak kitni branches se hoke aayi, kis transfer_no se.
    """
    # ✅ CHANGE: IsBranchRole → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        
        # ✅ CHANGE: getattr(user, 'branch', None) → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)

        search = request.GET.get('search', '').strip()
        transfer_filter = request.GET.get('transfer_no', '').strip()

        b2b_items = B2BStockTransferItem.objects.filter(
            transfer__to_branch=branch,
            is_received=True,
        ).select_related(
            'transfer', 'transfer__from_branch', 'from_item', 'from_variant', 'to_variant'
        ).order_by('-transfer__created_at')

        if search:
            b2b_items = b2b_items.filter(
                Q(from_item_name__icontains=search) |
                Q(from_barcode__icontains=search) |
                Q(transfer__transfer_no__icontains=search)
            )
        if transfer_filter:
            b2b_items = b2b_items.filter(transfer__transfer_no__icontains=transfer_filter)

        returned_qty_map = {}
        for r in B2BStockReturnItem.objects.filter(
            source_b2b_transfer_item__isnull=False,
            return_request__branch=branch
        ).values('source_b2b_transfer_item_id').annotate(total_returned=SumModel('quantity')):
            returned_qty_map[r['source_b2b_transfer_item_id']] = r['total_returned'] or 0

        company_branch = _get_company_branch()

        data = []
        for item in b2b_items:
            total_received = item.quantity
            total_returned = returned_qty_map.get(item.id, 0)
            remaining_qty = total_received - total_returned
            if remaining_qty <= 0:
                continue

            from_item = item.from_item
            from_variant = item.from_variant

            company_variant_id = None
            if company_branch:
                cv = ItemVariants.objects.filter(
                    barcode=item.from_barcode,
                    item__branch=company_branch,
                    item__created_by_superadmin=True,
                ).first()
                company_variant_id = cv.id if cv else None

            data.append({
                'id': item.id,
                'item_name': item.from_item_name,
                'variant_info': item.from_variant_info,
                'barcode': item.from_barcode,
                'quantity': remaining_qty,
                'original_quantity': total_received,
                'returned_quantity': total_returned,
                'rate': item.rate,
                'branch_variant_id': item.to_variant.id if item.to_variant else None,
                'company_variant_id': company_variant_id,
                'transfer_no': item.transfer.transfer_no,
                'transfer_id': item.transfer.id,
                'from_branch_name': item.transfer.from_branch.branch_name,
                'transfer_date': str(item.transfer.transfer_date),
                'hsnCode': getattr(from_item, 'hsnCode', ''),
                'taxSlab': getattr(from_item, 'taxSlab', ''),
                'size': getattr(from_variant, 'size', ''),
                'color': getattr(from_variant, 'color', ''),
                'transfer_chain': build_transfer_chain(branch, item.from_barcode),
            })

        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response({
            'success': True,
            'data': paginated,
            'total_items': len(data),
        })


# ════════════════════════════════════════════════════════════
# BRANCH: Create B2B return from selected items
# ════════════════════════════════════════════════════════════
class B2BStockReturnCreateView(APIView):
    """
    Branch multiple B2B-received items select karke, custom quantity ke
    saath return create karti hai. Hamesha superadmin (company) branch
    ko jaata hai.
    """
    # ✅ CHANGE: IsBranchRole → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        user = request.user
        
        # ✅ CHANGE: getattr(user, 'branch', None) → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)

        items_data = request.data.get('items', [])
        return_date = request.data.get('return_date')
        note = request.data.get('note', '')

        if not items_data:
            return Response({'success': False, 'message': 'No items selected.'}, status=400)

        company_branch = _get_company_branch()
        if not company_branch:
            return Response({'success': False, 'message': 'Company branch not found.'}, status=400)

        item_ids = [i['item_id'] for i in items_data]
        transfer_items = B2BStockTransferItem.objects.filter(
            id__in=item_ids,
            transfer__to_branch=branch,
            is_received=True,
        ).select_related('transfer', 'transfer__from_branch', 'from_item', 'from_variant', 'to_variant')

        if not transfer_items.exists():
            return Response({'success': False, 'message': 'No valid items found.'}, status=400)

        transfer_items_map = {it.id: it for it in transfer_items}

        already_returned_map = {}
        for row in B2BStockReturnItem.objects.filter(
            source_b2b_transfer_item_id__in=item_ids
        ).values('source_b2b_transfer_item_id').annotate(total=SumModel('quantity')):
            already_returned_map[row['source_b2b_transfer_item_id']] = row['total'] or 0

        first_transfer_item = next(iter(transfer_items_map.values()), None)

        with transaction.atomic():
            return_request = B2BStockReturn.objects.create(
                branch=branch,
                to_branch=company_branch,
                source_b2b_transfer=first_transfer_item.transfer if first_transfer_item else None,
                return_date=return_date,
                note=note,
                status='pending',
                created_by=user,
            )

            any_item_created = False

            for item_data in items_data:
                item_id = item_data['item_id']
                return_qty = item_data.get('quantity', 0)
                if return_qty <= 0:
                    continue

                transfer_item = transfer_items_map.get(item_id)
                if not transfer_item:
                    continue

                already_returned = already_returned_map.get(transfer_item.id, 0)
                remaining_qty = transfer_item.quantity - already_returned
                if return_qty > remaining_qty:
                    return_request.delete()
                    return Response({
                        'success': False,
                        'message': (
                            f"Return quantity ({return_qty}) cannot exceed remaining "
                            f"quantity ({remaining_qty}) for {transfer_item.from_item_name}"
                        )
                    }, status=400)

                from_item = transfer_item.from_item
                from_variant = transfer_item.from_variant

                branch_variant = transfer_item.to_variant
                if not branch_variant:
                    branch_variant = ItemVariants.objects.filter(
                        barcode=transfer_item.from_barcode,
                        item__branch=branch,
                        item__created_by_superadmin=True,
                    ).first()
                    if branch_variant:
                        transfer_item.to_variant = branch_variant
                        transfer_item.save(update_fields=['to_variant'])

                if not branch_variant:
                    return_request.delete()
                    return Response({
                        'success': False,
                        'message': f"'{transfer_item.from_item_name}' no matching item found in branch."
                    }, status=400)

                company_variant = ItemVariants.objects.filter(
                    barcode=transfer_item.from_barcode,
                    item__branch=company_branch,
                    item__created_by_superadmin=True,
                ).first()

                if not company_variant:
                    return_request.delete()
                    return Response({
                        'success': False,
                        'message': f"'{transfer_item.from_item_name}' has no matching company item to return against."
                    }, status=400)

                tax_percent = getattr(from_item, 'taxSlab', '0') or "0"
                same_state = (branch.state or "") == (company_branch.state or "")
                gst_result = calculate_gst_split(
                    transfer_item.rate, return_qty, tax_percent, False, same_state
                )

                B2BStockReturnItem.objects.create(
                    return_request=return_request,
                    source_b2b_transfer_item=transfer_item,
                    branch_variant=branch_variant,
                    company_variant=company_variant,
                    item_name=transfer_item.from_item_name,
                    variant_info=transfer_item.from_variant_info,
                    barcode=transfer_item.from_barcode,
                    size=getattr(from_variant, 'size', '') or '',
                    color=getattr(from_variant, 'color', '') or '',
                    hsnCode=getattr(from_item, 'hsnCode', '') or '',
                    taxSlab=tax_percent,
                    quantity=return_qty,
                    rate=transfer_item.rate,
                    tax_percent=tax_percent,
                    basic_amount=gst_result["basic_amount"],
                    tax_amount=gst_result["tax_amount"],
                    cgst=gst_result["cgst"],
                    sgst=gst_result["sgst"],
                    igst=gst_result["igst"],
                    net_amount=gst_result["net_amount"],
                )
                any_item_created = True

            if not any_item_created:
                return_request.delete()
                return Response({
                    'success': False,
                    'message': 'No valid items with quantity > 0 to return.'
                }, status=400)

        return Response({
            'success': True,
            'message': f'Return {return_request.return_no} created successfully!',
            'data': B2BStockReturnDetailSerializer(return_request).data
        }, status=201)


# ════════════════════════════════════════════════════════════
# BRANCH: List own B2B returns / SUPERADMIN: all
# ════════════════════════════════════════════════════════════
class B2BStockReturnListView(APIView):
    """List B2B returns"""
    
    # ✅ CHANGE: IsBranchRole → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        
        if user.role == 'superadmin':
            qs = B2BStockReturn.objects.prefetch_related('items').order_by('-created_at')
        else:
            # ✅ CHANGE: getattr(user, 'branch', None) → get_effective_branch()
            branch = user.get_effective_branch()
            if not branch:
                return Response({'success': False, 'message': 'No branch assigned.'}, status=400)
            qs = B2BStockReturn.objects.filter(branch=branch).prefetch_related('items').order_by('-created_at')

        status_filter = request.GET.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)

        search = request.GET.get('search', '')
        if search:
            qs = qs.filter(
                Q(return_no__icontains=search) |
                Q(branch__branch_name__icontains=search)
            )

        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = B2BStockReturnListSerializer(paginated, many=True)
        return paginator.get_paginated_response({'success': True, 'data': serializer.data})


# ════════════════════════════════════════════════════════════
# BRANCH/SUPERADMIN: Return detail
# ════════════════════════════════════════════════════════════
class B2BStockReturnDetailView(APIView):
    """Get B2B return detail"""
    
    # ✅ CHANGE: IsBranchRole → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, return_id):
        user = request.user
        
        try:
            if user.role == 'superadmin':
                return_request = B2BStockReturn.objects.get(id=return_id)
            else:
                # ✅ CHANGE: getattr(user, 'branch', None) → get_effective_branch()
                branch = user.get_effective_branch()
                if not branch:
                    return Response({'success': False, 'message': 'No branch assigned.'}, status=400)
                return_request = B2BStockReturn.objects.get(id=return_id, branch=branch)
        except B2BStockReturn.DoesNotExist:
            return Response({'success': False, 'message': 'Return not found.'}, status=404)

        serializer = B2BStockReturnDetailSerializer(return_request)
        return Response({'success': True, 'data': serializer.data})


# ════════════════════════════════════════════════════════════
# BRANCH: Update packaging status (deduct branch stock)
# ════════════════════════════════════════════════════════════
class B2BReturnPackagingUpdateView(APIView):
    """Branch marks items as packaging ready"""
    
    # ✅ CHANGE: IsBranchRole → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user
        
        if user.role == 'superadmin':
            return Response({'success': False, 'message': 'Branch only action.'}, status=400)

        # ✅ CHANGE: getattr(user, "branch", None) → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)

        try:
            return_request = B2BStockReturn.objects.get(id=return_id, branch=branch)
        except B2BStockReturn.DoesNotExist:
            return Response({'success': False, 'message': 'Return not found.'}, status=404)

        if return_request.status in ['received', 'rejected', 'cancelled']:
            return Response({
                'success': False,
                'message': f'Cannot update packaging. Current status: {return_request.status}'
            }, status=400)

        serializer = B2BReturnItemStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'errors': serializer.errors}, status=400)

        item_ids = serializer.validated_data['item_ids']
        is_packaging_ready = serializer.validated_data['is_packaging_ready']

        with transaction.atomic():
            items_updated = B2BStockReturnItem.objects.filter(
                return_request=return_request, id__in=item_ids
            ).update(is_packaging_ready=is_packaging_ready)

            if is_packaging_ready:
                for return_item in B2BStockReturnItem.objects.filter(
                    return_request=return_request, id__in=item_ids, is_packaging_ready=True
                ):
                    branch_variant = return_item.branch_variant
                    if branch_variant:
                        old_stock = branch_variant.current_stock or 0
                        new_stock = max(0, old_stock - return_item.quantity)
                        branch_variant.current_stock = new_stock
                        branch_variant.save(update_fields=['current_stock'])

            all_items = return_request.items.all()
            total_count = all_items.count()
            ready_count = all_items.filter(is_packaging_ready=True).count()

            if ready_count == total_count and total_count > 0:
                return_request.status = 'packaging_ready'
                return_request.save(update_fields=['status', 'updated_at'])
                message = 'All items packaging ready. Stock deducted from branch.'
            else:
                if return_request.status == 'packaging_ready':
                    return_request.status = 'pending'
                    return_request.save(update_fields=['status', 'updated_at'])
                message = f'{items_updated} item(s) updated. {ready_count}/{total_count} ready.'

        return Response({
            'success': True,
            'message': message,
            'data': {
                'items_updated': items_updated,
                'ready_count': ready_count,
                'total_count': total_count,
                'current_status': return_request.status,
            }
        })


# ════════════════════════════════════════════════════════════
# SUPERADMIN: Approve or Reject
# ════════════════════════════════════════════════════════════
class B2BReturnApproveRejectView(APIView):
    """Superadmin approves or rejects B2B return"""
    
    # ✅ CHANGE: IsSuperAdminRole → IsSuperAdminOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/b2bstockReturnverification"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user
        
        try:
            return_request = B2BStockReturn.objects.get(id=return_id)
        except B2BStockReturn.DoesNotExist:
            return Response({'success': False, 'message': 'Return not found.'}, status=404)

        if return_request.status not in ['pending', 'packaging_ready']:
            return Response({
                'success': False,
                'message': f'Cannot process return. Current status: {return_request.status}'
            }, status=400)

        action = request.data.get('action')
        note = request.data.get('note', '')

        if action not in ['approve', 'reject']:
            return Response({'success': False, 'message': 'Action must be "approve" or "reject".'}, status=400)

        with transaction.atomic():
            if action == 'approve':
                return_request.status = 'approved'
                return_request.approved_by = user
                return_request.save(update_fields=['status', 'approved_by', 'updated_at'])
                message = f'Return {return_request.return_no} approved.'
            else:
                return_request.status = 'rejected'
                return_request.note = note if note else (return_request.note or '')
                update_fields = ['status', 'updated_at']
                if note:
                    update_fields.append('note')
                return_request.save(update_fields=update_fields)
                message = f'Return {return_request.return_no} rejected.'

        return Response({
            'success': True,
            'message': message,
            'data': B2BStockReturnDetailSerializer(return_request).data
        })


# ════════════════════════════════════════════════════════════
# SUPERADMIN: Receive (company stock increase)
# ════════════════════════════════════════════════════════════
class B2BReturnReceiveView(APIView):
    """Superadmin receives returned items - STOCK INCREASE"""
    
    # ✅ CHANGE: IsSuperAdminRole → IsSuperAdminOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/b2bstockReturnverification"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user
        
        try:
            return_request = B2BStockReturn.objects.get(id=return_id)
        except B2BStockReturn.DoesNotExist:
            return Response({'success': False, 'message': 'Return not found.'}, status=404)

        if return_request.status not in ['approved', 'packaging_ready']:
            return Response({
                'success': False,
                'message': f'Return must be approved and packaged first. Current status: {return_request.status}'
            }, status=400)

        all_items = return_request.items.all()
        total_count = all_items.count()
        ready_count = all_items.filter(is_packaging_ready=True).count()

        if total_count == 0 or ready_count != total_count:
            return Response({
                'success': False,
                'message': f'Cannot receive. Only {ready_count}/{total_count} items are packaged by branch.'
            }, status=400)

        with transaction.atomic():
            for return_item in return_request.items.all():
                if return_item.is_returned_to_company:
                    continue

                company_variant = return_item.company_variant
                if not company_variant:
                    continue

                old_company_stock = company_variant.current_stock or 0
                company_variant.current_stock = old_company_stock + return_item.quantity
                company_variant.save(update_fields=['current_stock'])

                return_item.is_returned_to_company = True
                return_item.save(update_fields=['is_returned_to_company'])

            return_request.status = 'received'
            return_request.received_by = user
            return_request.save(update_fields=['status', 'received_by', 'updated_at'])

        return Response({
            'success': True,
            'message': f'Return {return_request.return_no} received. Stock increased in company branch.',
            'data': B2BStockReturnDetailSerializer(return_request).data
        })


# ════════════════════════════════════════════════════════════
# BRANCH: Cancel
# ════════════════════════════════════════════════════════════
class B2BReturnCancelView(APIView):
    """Branch cancels their B2B return request"""
    
    # ✅ CHANGE: IsBranchRole → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user
        
        # ✅ CHANGE: getattr(user, 'branch', None) → get_effective_branch()
        branch = user.get_effective_branch()
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)

        try:
            return_request = B2BStockReturn.objects.get(id=return_id, branch=branch)
        except B2BStockReturn.DoesNotExist:
            return Response({'success': False, 'message': 'Return not found.'}, status=404)

        if return_request.status in ['received', 'rejected']:
            return Response({'success': False, 'message': f'Cannot cancel. Status: {return_request.status}'}, status=400)

        return_request.status = 'cancelled'
        return_request.save(update_fields=['status', 'updated_at'])
        return Response({'success': True, 'message': f'Return {return_request.return_no} cancelled.'})


# ════════════════════════════════════════════════════════════
# SUPERADMIN: All B2B returns list (admin management page ke liye)
# ════════════════════════════════════════════════════════════
class AdminB2BReturnListView(APIView):
    """Superadmin ke liye - all B2B returns from all branches"""
    
    # ✅ CHANGE: IsSuperAdminRole → IsSuperAdminOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrPagePermittedEmployee]
    page_key = "/b2bstockReturnverification"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        qs = B2BStockReturn.objects.prefetch_related('items').order_by('-created_at')

        status_filter = request.GET.get('status', '')
        if status_filter:
            qs = qs.filter(status=status_filter)

        branch_filter = request.GET.get('branch_id', '')
        if branch_filter and branch_filter.isdigit():
            qs = qs.filter(branch_id=int(branch_filter))

        search = request.GET.get('search', '')
        if search:
            qs = qs.filter(
                Q(return_no__icontains=search) |
                Q(branch__branch_name__icontains=search)
            )

        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = B2BStockReturnListSerializer(paginated, many=True)
        return paginator.get_paginated_response({'success': True, 'data': serializer.data})


# ════════════════════════════════════════════════════════════
# Next return number preview (estimate, no increment)
# ════════════════════════════════════════════════════════════
class NextB2BReturnNumberPreviewView(APIView):
    """GET /api/b2b-stock-returns/next-number-preview/"""
    
    # ✅ CHANGE: permission_classes = [] → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/b2bstockReturn"  # ✅ ADD: Frontend route
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        
        # ✅ CHANGE: get_effective_branch() for both superadmin and branch
        branch = user.get_effective_branch()
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)

        from pos.models.settings import setting
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, 'SR', 'RTN') if settings_obj else 'RTN'

        fy = get_financial_year()
        branch_code = ""
        if branch.branch_code:
            branch_code = branch.branch_code.strip().upper()

        seq = B2BReturnSequence.objects.filter(financial_year=fy).first()
        next_no = (seq.last_number if seq else 0) + 1
        next_no_str = str(next_no).zfill(4)

        if branch_code:
            preview = f"{prefix}/B2B/{branch_code}/{fy}/{next_no_str}"
        else:
            preview = f"{prefix}/B2B/{fy}/{next_no_str}"

        same_state = None
        company_branch = _get_company_branch()
        if company_branch:
            same_state = (
                (branch.state or '').strip().lower() == (company_branch.state or '').strip().lower()
            )

        return Response({'success': True, 'next_return_no': preview, 'same_state': same_state})