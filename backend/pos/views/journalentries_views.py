# views/journal_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.core.exceptions import ValidationError
from pos.models.journalentries import JournalEntry,JournalMaster
from pos.serializers.journalentries_serializers import JournalMasterSerializer


class JournalCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

    def get(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response({"detail": "User does not have a branch assigned."},
                            status=status.HTTP_400_BAD_REQUEST)
        payments = JournalMaster.objects.filter(branch=branch)
        serializer = JournalMasterSerializer(payments, many=True)
        return Response(serializer.data)

    def post(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response({"detail": "User does not have a branch assigned."},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = JournalMasterSerializer(data=request.data, context={"branch": branch})
        if serializer.is_valid():
            try:
                serializer.save()
            except ValidationError as e:
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
