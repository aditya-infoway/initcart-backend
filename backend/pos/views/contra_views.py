#pos/views/contra_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError
from django.db import transaction

from pos.models.contra import Contra
from pos.serializers.contra_serializers import ContraSerializer

class ContraCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

    def get(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response({"detail": "User does not have a branch assigned."},
                            status=status.HTTP_400_BAD_REQUEST)
        payments = Contra.objects.filter(branch=branch).order_by('-created_at')
        serializer = ContraSerializer(payments, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response({"detail": "User does not have a branch assigned."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Validate voucher number uniqueness
        voucher_no = request.data.get('voucher_no')
        if Contra.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            return Response(
                {"detail": "Voucher number already exists. Please regenerate."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ContraSerializer(data=request.data, context={"branch": branch})
        if serializer.is_valid():
            try:
                instance = serializer.save()
                return Response(ContraSerializer(instance).data, status=status.HTTP_201_CREATED)
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)