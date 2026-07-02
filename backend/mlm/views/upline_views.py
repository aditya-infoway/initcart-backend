from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.upline_engine import get_upline_agents


class AgentUplineAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        uplines = get_upline_agents(request.user)

        data = []

        for u in uplines:

            data.append({

                "level": u["level"],
                "user_id": u["user"].id,
                "name": u["user"].first_name,
                "email": u["user"].email

            })

        return Response(data)