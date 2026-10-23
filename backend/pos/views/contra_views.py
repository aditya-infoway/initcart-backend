# pos/views/contra_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction

from pos.models.contra import Contra
from pos.serializers.contra_serializers import ContraSerializer

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


class ContraCreateView(APIView):
    """Create and list contra entries (Cash Deposit, Cash Withdrawal, Bank Transfer)"""
    
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Contra"

    def get_branch(self, user):
        return user.get_effective_branch()

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'
        is_employee = user.role == 'employee'

        branch = user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Employee ko bhi branch_id override allow (jaise baki modules me)
        branch_id_param = request.GET.get('branch_id')
        if branch_id_param:
            if is_superadmin or is_employee:
                from pos.models.branch import Branch
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)

        payments = Contra.objects.filter(branch=branch).order_by('-created_at')

        # ✅ NEW: Server-side search
        search = request.GET.get('search', '').strip()
        if search:
            from django.db.models import Q
            payments = payments.filter(
                Q(voucher_no__icontains=search) |
                Q(cash_account__account_name__icontains=search) |
                Q(op_account__account_name__icontains=search) |
                Q(narration__icontains=search)
            )

        # ✅ NEW: Server-side type filter
        type_param = request.GET.get('type', '').strip()
        if type_param:
            payments = payments.filter(type=type_param)

        # ✅ NEW: Pagination
        from pos.utils.pagination import StandardResultsSetPagination
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(payments, request)
        serializer = ContraSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @transaction.atomic
    def post(self, request):
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        # ✅ Branch-wise voucher uniqueness check (moved to serializer)
        # Serializer will handle validation now 

        serializer = ContraSerializer(data=request.data, context={"branch": branch, "request": request})
        if serializer.is_valid():
            try:
                instance = serializer.save()
                return Response(ContraSerializer(instance).data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)