# mlm/views/agent_eligibility_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings


class AgentEligibilityCheckAPIView(APIView):
    """
    Check if an agent is eligible to refer new agents
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            agent = Agent.objects.get(user=request.user, status="approved")
            
            can_refer, message = agent.can_refer_agents()
            
            settings = MLMSettings.objects.first()
            
            return Response({
                'can_refer': can_refer,
                'message': message,
                'total_sales': agent.total_sales,
                'minimum_sales_required': settings.minimum_sale_amount if settings else 0,
                'remaining_sales_needed': max(0, (settings.minimum_sale_amount - agent.total_sales)) if settings else 0,
                'is_active': agent.is_active_agent,
                'status': agent.status
            })
            
        except Agent.DoesNotExist:
            return Response({
                'can_refer': False,
                'message': 'You are not an approved agent',
                'total_sales': 0,
                'minimum_sales_required': 0,
                'remaining_sales_needed': 0,
                'is_active': False,
                'status': 'not_found'
            }, status=404)