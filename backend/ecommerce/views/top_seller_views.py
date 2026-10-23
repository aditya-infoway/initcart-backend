from django.db import transaction
from django.db.models import Q, Max
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework.response import Response

from ecommerce.models.vendor import Vendor
from ecommerce.models.top_seller import TopSellerRequest
from ecommerce.serializers.top_seller_serializers import (
    TopSellerRequestSerializer, CreateTopSellerRequestSerializer,
    ApproveTopSellerSerializer, RejectTopSellerSerializer,
    BannerUploadSerializer, get_vendor_logo,
)
from ecommerce.utils.top_seller_helpers import process_banner, get_banner_url
from ecommerce.permissions import IsSuperAdmin
from pos.utils.pagination import StandardReportPagination


def _get_vendor(user):
    try:
        return Vendor.objects.get(user=user)
    except Vendor.DoesNotExist:
        return None


def _not_found(msg='Top seller request not found'):
    return Response({'success': False, 'message': msg}, status=status.HTTP_404_NOT_FOUND)


def _first_error(errors):
    """Extract one readable message from serializer errors."""
    if isinstance(errors, dict):
        for v in errors.values():
            return _first_error(v)
    if isinstance(errors, (list, tuple)) and errors:
        return _first_error(errors[0])
    return str(errors)

def _order_conflict(order, exclude_pk=None):
    """Return the approved request that already uses this display order, or None."""
    qs = TopSellerRequest.objects.filter(
        status='approved', display_order=order
    ).select_related('vendor')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.first()


# ============== VENDOR SIDE ==============

class VendorTopSellerListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardReportPagination

    def get(self, request):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                            status=status.HTTP_404_NOT_FOUND)

        qs = TopSellerRequest.objects.filter(vendor=vendor)
        has_open = qs.filter(status__in=['pending', 'approved']).exists()
        can_request = bool(getattr(vendor, 'is_approved', False)) and not has_open

        # Latest request is always sent separately, independent of the current page
        latest_obj = qs.first()
        latest = (TopSellerRequestSerializer(latest_obj, context={'request': request}).data
                  if latest_obj else None)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = TopSellerRequestSerializer(page, many=True, context={'request': request}).data

        response = paginator.get_paginated_response(data)
        response.data['latest'] = latest
        response.data['can_request'] = can_request
        response.data['store_approved'] = bool(getattr(vendor, 'is_approved', False))
        response.data['vendor_name'] = vendor.business_name
        return response
class VendorTopSellerCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        vendor = _get_vendor(request.user)
        if not vendor:
            return Response({'success': False, 'message': 'Vendor profile not found'},
                            status=status.HTTP_404_NOT_FOUND)

        serializer = CreateTopSellerRequestSerializer(
            data=request.data, context={'request': request, 'vendor': vendor}
        )
        if not serializer.is_valid():
            return Response({'success': False, 'message': _first_error(serializer.errors),
                             'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        obj = serializer.save()
        return Response({
            'success': True,
            'message': 'Top Seller request submitted successfully',
            'data': TopSellerRequestSerializer(obj, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


# ============== SUPERADMIN SIDE ==============

class AdminTopSellerListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    pagination_class = StandardReportPagination

    def get(self, request):
        base = TopSellerRequest.objects.select_related('vendor', 'vendor__user')

        # Stats are always calculated on the full table, not on the current page
        stats = {
            'total': base.count(),
            'pending': base.filter(status='pending').count(),
            'approved': base.filter(status='approved').count(),
            'live': base.filter(status='approved', is_active=True).count(),
            'hidden': base.filter(status='approved', is_active=False).count(),
            'rejected': base.filter(status='rejected').count(),
        }

        qs = base
        status_filter = request.query_params.get('status')
        if status_filter and status_filter != 'all':
            if status_filter == 'live':
                qs = qs.filter(status='approved', is_active=True)
            elif status_filter == 'hidden':
                qs = qs.filter(status='approved', is_active=False)
            else:
                qs = qs.filter(status=status_filter)

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(Q(vendor__business_name__icontains=search) | Q(request_id__icontains=search))

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = TopSellerRequestSerializer(page, many=True, context={'request': request}).data

        response = paginator.get_paginated_response(data)
        response.data['stats'] = stats
        return response
class AdminTopSellerDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def get(self, request, pk):
        try:
            obj = TopSellerRequest.objects.select_related('vendor', 'vendor__user').get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()
        return Response({'success': True,
                         'data': TopSellerRequestSerializer(obj, context={'request': request}).data})

    def delete(self, request, pk):
        """Remove the entry completely (vendor can send a new request later)."""
        try:
            obj = TopSellerRequest.objects.get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()
        if obj.banner:
            obj.banner.delete(save=False)
        obj.delete()
        return Response({'success': True, 'message': 'Top seller entry removed'})


class AdminTopSellerApproveAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    @transaction.atomic
    def post(self, request, pk):
        try:
            obj = TopSellerRequest.objects.select_for_update().get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()

        serializer = ApproveTopSellerSerializer(data=request.data, context={'top_seller': obj})
        if not serializer.is_valid():
            return Response({'success': False, 'message': _first_error(serializer.errors),
                             'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        vd = serializer.validated_data
        order = vd.get('display_order')
        if order is None:
            # Automatic order: always one more than the highest used number, so it is never a duplicate
            max_order = TopSellerRequest.objects.filter(status='approved').aggregate(m=Max('display_order'))['m']
            order = (max_order or 0) + 1
        else:
            conflict = _order_conflict(order, exclude_pk=obj.pk)
            if conflict:
                return Response({
                    'success': False,
                    'message': f'Order number {order} is already used by "{conflict.vendor.business_name}". '
                               f'Please choose a different number.',



                               
                }, status=status.HTTP_400_BAD_REQUEST)

        obj.status = 'approved'
        obj.is_active = vd.get('is_active', True)
        obj.display_order = order
        obj.admin_remarks = vd.get('remarks', '')
        obj.approved_at = timezone.now()
        obj.rejected_at = None
        obj.save()

        return Response({
            'success': True,
            'message': 'Top seller request approved',
            'data': TopSellerRequestSerializer(obj, context={'request': request}).data,
        })


class AdminTopSellerRejectAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            obj = TopSellerRequest.objects.get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()

        serializer = RejectTopSellerSerializer(data=request.data, context={'top_seller': obj})
        if not serializer.is_valid():
            return Response({'success': False, 'message': _first_error(serializer.errors),
                             'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        obj.status = 'rejected'
        obj.is_active = False
        obj.admin_remarks = serializer.validated_data['remarks']
        obj.rejected_at = timezone.now()
        obj.save()
        return Response({'success': True, 'message': 'Top seller request rejected'})


class AdminTopSellerToggleAPIView(APIView):
    """Show or hide an approved vendor on the website."""
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        try:
            obj = TopSellerRequest.objects.get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()

        if obj.status != 'approved':
            return Response({'success': False, 'message': 'Only approved sellers can be shown/hidden'},
                            status=status.HTTP_400_BAD_REQUEST)

        obj.is_active = not obj.is_active
        obj.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'success': True,
            'message': 'Seller is now visible on website' if obj.is_active else 'Seller hidden from website',
            'is_active': obj.is_active,
        })


class AdminTopSellerOrderAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]

    @transaction.atomic
    def post(self, request, pk):
        try:
            obj = TopSellerRequest.objects.select_for_update().get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()

        try:
            order = int(request.data.get('display_order'))
            if order < 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({'success': False, 'message': 'display_order must be a non-negative number'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Same order number cannot be used by two approved sellers
        conflict = _order_conflict(order, exclude_pk=obj.pk)
        if conflict:
            return Response({
                'success': False,
                'message': f'Order number {order} is already used by "{conflict.vendor.business_name}". '
                           f'Please choose a different number.',
            }, status=status.HTTP_400_BAD_REQUEST)

        obj.display_order = order
        obj.save(update_fields=['display_order', 'updated_at'])
        return Response({'success': True, 'message': 'Display order updated', 'display_order': order})


class AdminTopSellerBannerAPIView(APIView):
    """
    POST   -> upload / replace the banner (works before and after approval)
    DELETE -> remove the banner (the store logo is used as fallback in the slider)
    """
    permission_classes = [permissions.IsAuthenticated, IsSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            obj = TopSellerRequest.objects.select_related('vendor', 'vendor__user').get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()

        if obj.status == 'rejected':
            return Response({'success': False, 'message': 'Banner cannot be changed for a rejected request'},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = BannerUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'success': False, 'message': _first_error(serializer.errors),
                             'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        new_file = process_banner(serializer.validated_data['banner'])
        if obj.banner:
            obj.banner.delete(save=False)
        obj.banner = new_file
        obj.banner_uploaded_by = 'admin'
        obj.save()

        return Response({
            'success': True,
            'message': 'Banner updated',
            'data': TopSellerRequestSerializer(obj, context={'request': request}).data,
        })

    def delete(self, request, pk):
        try:
            obj = TopSellerRequest.objects.select_related('vendor', 'vendor__user').get(pk=pk)
        except TopSellerRequest.DoesNotExist:
            return _not_found()

        if obj.banner:
            obj.banner.delete(save=False)
        obj.banner = None
        obj.banner_uploaded_by = ''
        obj.save()

        return Response({
            'success': True,
            'message': 'Banner removed',
            'data': TopSellerRequestSerializer(obj, context={'request': request}).data,
        })


# ============== PUBLIC (WEBSITE SLIDER) ==============

class PublicTopSellersAPIView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        qs = (TopSellerRequest.objects
              .select_related('vendor')
              .filter(status='approved', is_active=True, vendor__is_approved=True)
              .order_by('display_order', '-approved_at'))

        data = [{
            'id': t.vendor.id,
            'business_name': t.vendor.business_name,
            'city': getattr(t.vendor, 'city', '') or '',
            'state': getattr(t.vendor, 'state', '') or '',
            'banner_url': get_banner_url(t, request),
            'store_logo_url': get_vendor_logo(t.vendor, request),
            'is_approved': True,
        } for t in qs]
        return Response(data)