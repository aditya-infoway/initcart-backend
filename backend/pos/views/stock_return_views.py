from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from pos.models.stock_return import StockReturn, StockReturnItem
from pos.models.branch import Branch
from pos.models.items import itemvariants, items
from pos.models.stock_transfer import StockTransfer, StockTransferItem
from pos.serializers.stock_return_serializers import (
    StockReturnCreateSerializer,
    StockReturnListSerializer,
    StockReturnDetailSerializer,
    ReturnStatusUpdateSerializer,
    ReturnItemStatusSerializer,
)
from pos.utils.pagination import StandardResultsSetPagination


class IsSuperAdminRole(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == 'superadmin'


class IsBranchRole(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user_role = request.user.role
        if user_role == 'superadmin':
            return True
        allowed_roles = ['branch', 'vendor', 'branch_both', 'branch_customer', 'branch_agent', 'branch_single']
        if user_role in allowed_roles or user_role.startswith('branch'):
            return True
        return False


# ════════════════════════════════════════════════════════════
# BRANCH: Get eligible transfers for return
# ════════════════════════════════════════════════════════════
class EligibleTransfersForReturnView(APIView):
    """
    Branch ke liye - jin transfers se return kar sakte hain
    Only completed transfers with verified items
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        
        # Get branch
        if user.role == 'superadmin':
            # Superadmin can't create returns from branch perspective
            return Response({
                'success': False,
                'message': 'Superadmin cannot create returns from here.'
            }, status=400)
        
        branch = getattr(user, 'branch', None)
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch assigned.'
            }, status=400)
        
        # Get all completed transfers to this branch with items
        transfers = StockTransfer.objects.filter(
            to_branch=branch,
            status='completed'
        ).exclude(
            # Exclude transfers that already have a return
            id__in=StockReturn.objects.filter(
                source_transfer__isnull=False
            ).values_list('source_transfer_id', flat=True)
        ).prefetch_related('items').order_by('-created_at')
        
        data = []
        for transfer in transfers:
            items = transfer.items.filter(is_stock_updated=True)
            if not items.exists():
                continue
            
            data.append({
                'id': transfer.id,
                'transfer_no': transfer.transfer_no,
                'transfer_date': transfer.transfer_date,
                'from_branch_name': transfer.from_branch.branch_name,
                'item_count': items.count(),
                'total_quantity': sum(item.quantity for item in items),
                'transfer_type': transfer.transfer_type,
                'source_order_no': transfer.source_order.order_id if transfer.source_order else None,
            })
        
        return Response({
            'success': True,
            'data': data,
            'count': len(data),
        })


# ════════════════════════════════════════════════════════════
# BRANCH: Create return request
# ════════════════════════════════════════════════════════════
class StockReturnCreateView(APIView):
    """
    Branch creates a return request
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        user = request.user
        
        if user.role == 'superadmin':
            return Response({
                'success': False,
                'message': 'Superadmin cannot create returns.'
            }, status=400)
        
        serializer = StockReturnCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            try:
                return_request = serializer.save()
                detail_serializer = StockReturnDetailSerializer(return_request)
                return Response({
                    'success': True,
                    'message': f'Return {return_request.return_no} created successfully!',
                    'data': detail_serializer.data
                }, status=201)
            except Exception as e:
                return Response({
                    'success': False,
                    'message': str(e)
                }, status=400)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=400)


# ════════════════════════════════════════════════════════════
# BRANCH: List returns
# ════════════════════════════════════════════════════════════
class StockReturnListView(APIView):
    """
    Branch ke apne returns list
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        
        if user.role == 'superadmin':
            # Superadmin sees all returns
            qs = StockReturn.objects.prefetch_related('items').order_by('-created_at')
        else:
            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({
                    'success': False,
                    'message': 'No branch assigned.'
                }, status=400)
            qs = StockReturn.objects.filter(
                branch=branch
            ).prefetch_related('items').order_by('-created_at')
        
        # Filters
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
        serializer = StockReturnListSerializer(paginated, many=True)
        
        return paginator.get_paginated_response({
            'success': True,
            'data': serializer.data,
        })


# ════════════════════════════════════════════════════════════
# BRANCH/SUPERADMIN: Return detail
# ════════════════════════════════════════════════════════════
class StockReturnDetailView(APIView):
    """
    Return detail view
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request, return_id):
        user = request.user
        
        try:
            if user.role == 'superadmin':
                return_request = StockReturn.objects.get(id=return_id)
            else:
                branch = getattr(user, 'branch', None)
                if not branch:
                    return Response({
                        'success': False,
                        'message': 'No branch assigned.'
                    }, status=400)
                return_request = StockReturn.objects.get(
                    id=return_id,
                    branch=branch
                )
        except StockReturn.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Return not found.'
            }, status=404)
        
        serializer = StockReturnDetailSerializer(return_request)
        return Response({
            'success': True,
            'data': serializer.data,
        })


# ════════════════════════════════════════════════════════════
# BRANCH: Update packaging status
# ════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════
# BRANCH: Update packaging status
# ════════════════════════════════════════════════════════════
class ReturnPackagingUpdateView(APIView):
    """
    Branch marks items as packaging ready
    ✅ FIX: Now allows 'approved' status as well
    ✅ FIX: Removed broken StockHistory import (model doesn't exist).
       History is derived dynamically from StockReturnItem in StockHistoryAPIView,
       same pattern as StockTransferItem — no separate history model needed.
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user

        if user.role == 'superadmin':
            return Response({
                'success': False,
                'message': 'Branch only action.'
            }, status=400)

        branch = getattr(user, "branch", None)
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch assigned.'
            }, status=400)

        try:
            return_request = StockReturn.objects.get(id=return_id, branch=branch)
        except StockReturn.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Return not found.'
            }, status=404)

        # ✅ Allow 'pending' AND 'approved' status for packaging
        if return_request.status in ['received', 'rejected', 'cancelled']:
            return Response({
                'success': False,
                'message': f'Cannot update packaging. Current status: {return_request.status}'
            }, status=400)

        serializer = ReturnItemStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': serializer.errors
            }, status=400)

        item_ids = serializer.validated_data['item_ids']
        is_packaging_ready = serializer.validated_data['is_packaging_ready']

        with transaction.atomic():
            # ✅ STEP 1: Update items packaging status
            items_updated = StockReturnItem.objects.filter(
                return_request=return_request,
                id__in=item_ids
            ).update(
                is_packaging_ready=is_packaging_ready
            )

            # ✅ STEP 2: If marking as ready, DEDUCT stock from branch
            if is_packaging_ready:
                for return_item in StockReturnItem.objects.filter(
                    return_request=return_request,
                    id__in=item_ids,
                    is_packaging_ready=True
                ):
                    branch_variant = return_item.branch_variant
                    if branch_variant:
                        # Deduct stock from branch
                        old_stock = branch_variant.current_stock or 0
                        new_stock = max(0, old_stock - return_item.quantity)
                        branch_variant.current_stock = new_stock
                        branch_variant.save(update_fields=['current_stock'])
                        # ✅ No StockHistory model call here.
                        # History for this action is derived on read from
                        # StockReturnItem (is_packaging_ready=True) inside
                        # StockHistoryAPIView -> "Stock Return (Packaged)" entry.

            # ✅ STEP 3: Check if all items are packaging ready
            all_items = return_request.items.all()
            total_count = all_items.count()
            ready_count = all_items.filter(is_packaging_ready=True).count()

            if ready_count == total_count and total_count > 0:
                return_request.status = 'packaging_ready'
                return_request.save(update_fields=['status', 'updated_at'])
                message = 'All items packaging ready. Stock deducted from branch. Return is now in "Packaging Ready" status.'
            else:
                # Update status to pending if not all ready
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
# SUPERADMIN: Approve or Reject return
# ════════════════════════════════════════════════════════════
class ReturnApproveRejectView(APIView):
    """
    Superadmin approves or rejects return request
    """
    permission_classes = [IsSuperAdminRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user
        
        try:
            return_request = StockReturn.objects.get(id=return_id)
        except StockReturn.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Return not found.'
            }, status=404)
        
        if return_request.status not in ['pending', 'packaging_ready']:
            return Response({
                'success': False,
                'message': f'Cannot process return. Current status: {return_request.status}'
            }, status=400)
        
        action = request.data.get('action')  # 'approve' or 'reject'
        note = request.data.get('note', '')
        
        if action not in ['approve', 'reject']:
            return Response({
                'success': False,
                'message': 'Action must be "approve" or "reject".'
            }, status=400)
        
        with transaction.atomic():
            if action == 'approve':
                return_request.status = 'approved'
                return_request.approved_by = user
                return_request.save(update_fields=['status', 'approved_by', 'updated_at'])
                message = f'Return {return_request.return_no} approved.'
            else:
                return_request.status = 'rejected'
                return_request.note = note if note else (return_request.note or '')
                if note:
                    return_request.save(update_fields=['status', 'note', 'updated_at'])
                else:
                    return_request.save(update_fields=['status', 'updated_at'])
                message = f'Return {return_request.return_no} rejected.'
        
        return Response({
            'success': True,
            'message': message,
            'data': StockReturnDetailSerializer(return_request).data
        })


# ════════════════════════════════════════════════════════════
# SUPERADMIN: Receive return (stock increase in company)
# ════════════════════════════════════════════════════════════
class ReturnReceiveView(APIView):
    """
    Superadmin receives returned items - STOCK INCREASE HAPPENS HERE
    ✅ FIX: Now accepts both 'approved' AND 'packaging_ready' status.
       Flow: pending -> approved -> (branch packages, deducts branch stock)
             -> packaging_ready -> received (increases company stock only)
    ✅ FIX: Branch stock is NO LONGER deducted here — it was already
       deducted during the packaging step (ReturnPackagingUpdateView).
       Deducting again here was causing double stock deduction.
    """
    permission_classes = [IsSuperAdminRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user

        try:
            return_request = StockReturn.objects.get(id=return_id)
        except StockReturn.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Return not found.'
            }, status=404)

        # ✅ Accept both 'approved' and 'packaging_ready'
        if return_request.status not in ['approved', 'packaging_ready']:
            return Response({
                'success': False,
                'message': f'Return must be approved and packaged first. Current status: {return_request.status}'
            }, status=400)

        # ✅ Safety: make sure all items are actually packaging ready
        all_items = return_request.items.all()
        total_count = all_items.count()
        ready_count = all_items.filter(is_packaging_ready=True).count()

        if total_count == 0 or ready_count != total_count:
            return Response({
                'success': False,
                'message': f'Cannot receive. Only {ready_count}/{total_count} items are packaged by branch.'
            }, status=400)

        with transaction.atomic():
            # Process each item
            for return_item in return_request.items.all():
                if return_item.is_returned_to_company:
                    continue  # Already processed

                company_variant = return_item.company_variant
                if not company_variant:
                    continue

                # ✅ INCREASE COMPANY STOCK ONLY
                old_company_stock = company_variant.current_stock or 0
                new_company_stock = old_company_stock + return_item.quantity
                company_variant.current_stock = new_company_stock
                company_variant.save(update_fields=['current_stock'])
                # ✅ No StockHistory model call here.
                # History for this action is derived on read from
                # StockReturnItem (is_returned_to_company=True) inside
                # StockHistoryAPIView -> "Stock Return (Received)" entry.

                # ✅ REMOVED: Branch stock deduction.
                # Branch stock was already deducted during packaging step
                # (ReturnPackagingUpdateView). Deducting again here would
                # cause double deduction.

                # Mark as returned
                return_item.is_returned_to_company = True
                return_item.save(update_fields=['is_returned_to_company'])

            # Update return status
            return_request.status = 'received'
            return_request.received_by = user
            return_request.save(update_fields=['status', 'received_by', 'updated_at'])

        return Response({
            'success': True,
            'message': f'Return {return_request.return_no} received. Stock increased in company branch.',
            'data': StockReturnDetailSerializer(return_request).data
        })


# ════════════════════════════════════════════════════════════
# BRANCH: Cancel return
# ════════════════════════════════════════════════════════════
class ReturnCancelView(APIView):
    """
    Branch cancels their return request
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request, return_id):
        user = request.user
        branch = getattr(user, 'branch', None)
        
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch assigned.'
            }, status=400)
        
        try:
            return_request = StockReturn.objects.get(id=return_id, branch=branch)
        except StockReturn.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Return not found.'
            }, status=404)
        
        if return_request.status in ['received', 'rejected']:
            return Response({
                'success': False,
                'message': f'Cannot cancel. Status: {return_request.status}'
            }, status=400)
        
        return_request.status = 'cancelled'
        return_request.save(update_fields=['status', 'updated_at'])
        
        return Response({
            'success': True,
            'message': f'Return {return_request.return_no} cancelled.'
        })


# ════════════════════════════════════════════════════════════
# SUPERADMIN: All returns list
# ════════════════════════════════════════════════════════════
class AdminReturnListView(APIView):
    """
    Superadmin ke liye - all returns from all branches
    """
    permission_classes = [IsSuperAdminRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        qs = StockReturn.objects.prefetch_related('items').order_by('-created_at')
        
        # Filters
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
        serializer = StockReturnListSerializer(paginated, many=True)
        
        return paginator.get_paginated_response({
            'success': True,
            'data': serializer.data,
        })

class VerifiedItemsForReturnView(APIView):
    """
    Get all verified items from completed transfers
    ✅ SHOW: Sirf woh items jo abhi tak return nahi hue (remaining items)
    ✅ Agar 10 aaye the aur 5 return kiye, toh 5 remaining dikhenge
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def get(self, request):
        user = request.user
        branch = getattr(user, 'branch', None)
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)
        
        # Filters
        search = request.GET.get('search', '').strip()
        transfer_filter = request.GET.get('transfer_no', '').strip()
        
        # ✅ Base queryset - ALL verified items from completed transfers
        items = StockTransferItem.objects.filter(
            transfer__to_branch=branch,
            transfer__status='completed',
            is_stock_updated=True
        ).select_related(
            'transfer', 'from_item', 'from_variant', 'to_variant'
        ).order_by('-transfer__created_at')
        
        # ✅ Calculate remaining quantity for each item
        # Group by transfer_item_id and sum of returned quantities
        from django.db.models import Sum as SumModel
        
        # Get all return items grouped by source_transfer_item
        returned_qty_map = {}
        return_items = StockReturnItem.objects.filter(
            source_transfer_item__isnull=False,
            return_request__branch=branch
        ).values('source_transfer_item_id').annotate(
            total_returned=SumModel('quantity')
        )
        
        for r in return_items:
            returned_qty_map[r['source_transfer_item_id']] = r['total_returned'] or 0
        
        # Apply filters
        if search:
            items = items.filter(
                Q(from_item_name__icontains=search) |
                Q(from_barcode__icontains=search) |
                Q(transfer__transfer_no__icontains=search)
            )
        
        if transfer_filter:
            items = items.filter(transfer__transfer_no__icontains=transfer_filter)
        
        data = []
        for item in items:
            from_item = item.from_item
            from_variant = item.from_variant
            
            # ✅ Calculate remaining quantity
            total_received = item.quantity
            total_returned = returned_qty_map.get(item.id, 0)
            remaining_qty = total_received - total_returned
            
            # ✅ ONLY SHOW ITEMS WITH REMAINING QUANTITY > 0
            if remaining_qty <= 0:
                continue
            
            data.append({
                'id': item.id,
                'item_name': item.from_item_name,
                'variant_info': item.from_variant_info,
                'barcode': item.from_barcode,
                'quantity': remaining_qty,  # ✅ Remaining quantity (not received)
                'original_quantity': total_received,  # ✅ Original received quantity
                'returned_quantity': total_returned,  # ✅ Already returned quantity
                'rate': item.rate,
                'is_stock_updated': item.is_stock_updated,
                'branch_variant_id': item.to_variant.id if item.to_variant else None,
                'company_variant_id': item.from_variant.id if item.from_variant else None,
                'transfer_no': item.transfer.transfer_no,
                'transfer_id': item.transfer.id,
                'from_branch_name': item.transfer.from_branch.branch_name,
                'transfer_date': str(item.transfer.transfer_date),
                'hsnCode': getattr(from_item, 'hsnCode', ''),
                'taxSlab': getattr(from_item, 'taxSlab', ''),
                'size': getattr(from_variant, 'size', ''),
                'color': getattr(from_variant, 'color', ''),
            })
        
        # Pagination
        paginator = StandardResultsSetPagination()
        paginated = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response({
            'success': True,
            'data': paginated,
            'total_items': len(data),
        })
        
        
class StockReturnCreateFromItemsView(APIView):
    """
    Create return from multiple items with custom quantities
    Branch can return less than or equal to max quantity
    ✅ FIX: Now saves hsnCode, taxSlab, size, color on StockReturnItem
       creation — these were missing before, causing HSN/GST to show
       blank in the return detail view.
    """
    permission_classes = [IsBranchRole]
    authentication_classes = [JWTAuthentication, SessionAuthentication]

    def post(self, request):
        user = request.user
        branch = getattr(user, 'branch', None)
        if not branch:
            return Response({'success': False, 'message': 'No branch assigned.'}, status=400)
        
        items_data = request.data.get('items', [])  # List of {item_id, quantity}
        return_date = request.data.get('return_date')
        note = request.data.get('note', '')
        
        if not items_data:
            return Response({'success': False, 'message': 'No items selected.'}, status=400)
        
        # Get company branch
        from django.contrib.auth import get_user_model
        User = get_user_model()
        superadmin_user = User.objects.filter(role='superadmin').first()
        if not superadmin_user:
            return Response({'success': False, 'message': 'Superadmin not found.'}, status=400)
        
        try:
            company_branch = Branch.objects.get(user=superadmin_user)
        except Branch.DoesNotExist:
            return Response({'success': False, 'message': 'Company branch not found.'}, status=400)
        
        # Get selected items with quantities
        item_ids = [item['item_id'] for item in items_data]
        transfer_items = StockTransferItem.objects.filter(
            id__in=item_ids,
            transfer__to_branch=branch,
            is_stock_updated=True
        ).select_related('transfer', 'from_item', 'from_variant', 'to_variant')
        
        if not transfer_items.exists():
            return Response({'success': False, 'message': 'No valid items found.'}, status=400)
        
        # Check all items are from same transfer
        transfer_ids = set(item.transfer_id for item in transfer_items)
        if len(transfer_ids) > 1:
            return Response({
                'success': False,
                'message': 'All items must be from the same transfer.'
            }, status=400)
        
        transfer_id = transfer_ids.pop()
        source_transfer = StockTransfer.objects.get(id=transfer_id)
        
        # Check if return already exists
        if StockReturn.objects.filter(source_transfer=source_transfer).exists():
            return Response({
                'success': False,
                'message': 'Return already exists for this transfer.'
            }, status=400)
        
        with transaction.atomic():
            # Create return
            return_request = StockReturn.objects.create(
                branch=branch,
                to_branch=company_branch,
                source_transfer=source_transfer,
                source_order=source_transfer.source_order,
                return_date=return_date,
                note=note,
                status='pending',
                created_by=user,
            )
                
            # Create return items with custom quantities
            for item_data in items_data:
                item_id = item_data['item_id']
                return_qty = item_data.get('quantity', 0)
                
                if return_qty <= 0:
                    continue
                
                transfer_item = next((item for item in transfer_items if item.id == item_id), None)
                if not transfer_item:
                    continue
                
                # ✅ Check: Return quantity cannot exceed original quantity
                if return_qty > transfer_item.quantity:
                    return_request.delete()
                    return Response({
                        'success': False,
                        'message': f'Return quantity ({return_qty}) cannot exceed original quantity ({transfer_item.quantity}) for {transfer_item.from_item_name}'
                    }, status=400)
                
                # ✅ FIX: pull HSN/GST from the source item, and size/color
                # from the company variant — same as StockReturnCreateSerializer does.
                from_item = transfer_item.from_item
                from_variant = transfer_item.from_variant

                StockReturnItem.objects.create(
                    return_request=return_request,
                    source_transfer_item=transfer_item,
                    branch_variant=transfer_item.to_variant,
                    company_variant=transfer_item.from_variant,
                    item_name=transfer_item.from_item_name,
                    variant_info=transfer_item.from_variant_info,
                    barcode=transfer_item.from_barcode,
                    size=getattr(from_variant, 'size', '') or '',
                    color=getattr(from_variant, 'color', '') or '',
                    hsnCode=getattr(from_item, 'hsnCode', '') or '',
                    taxSlab=getattr(from_item, 'taxSlab', '') or '',
                    quantity=return_qty,
                    rate=transfer_item.rate,
                )
        
        return Response({
            'success': True,
            'message': f'Return {return_request.return_no} created successfully!',
            'data': StockReturnDetailSerializer(return_request).data
        }, status=201)            