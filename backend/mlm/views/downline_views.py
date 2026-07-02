from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from users.models import User


class AgentDownlineAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        downlines = User.objects.filter(referred_by=request.user)

        data = []

        for user in downlines:

            data.append({

                "user_id": user.id,
                "name": user.first_name,
                "email": user.email

            })

        return Response(data)