#mlm/views/tree_views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from users.utils.permissions import IsSuperAdmin

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication

from mlm.models.agent import Agent
from mlm.serializers.tree_serializer import DownlineTreeSerializer
from users.models import User


class AgentDownlineTreeAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        try:
            agent = Agent.objects.get(user=request.user, status="approved")
        except Agent.DoesNotExist:
            return Response({"error": "Agent not found"}, status=404)

        serializer = DownlineTreeSerializer(agent)

        return Response(serializer.data)
    
class AgentDirectDownlinesAPIView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        children_users = User.objects.filter(referred_by=user)

        agents = Agent.objects.filter(user__in=children_users)

        data = []

        for agent in agents:

            data.append({
                "id": agent.id,
                "full_name": agent.full_name,
                "agent_type": agent.agent_type,
                "city": agent.city,
                "state": agent.state
            })

        return Response(data)


class AdminAgentTreeAPIView(APIView):

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def get(self, request):

        # Root agents → jinke paas koi referral parent nahi
        root_users = User.objects.filter(referred_by=None)

        root_agents = Agent.objects.filter(
            user__in=root_users,
            status="approved"
        )

        serializer = DownlineTreeSerializer(root_agents, many=True)

        return Response(serializer.data)    
    
        
        
