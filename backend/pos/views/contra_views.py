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
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        payments = Contra.objects.filter(branch=branch).order_by('-created_at')
        serializer = ContraSerializer(payments, many=True)
        return Response(serializer.data)

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