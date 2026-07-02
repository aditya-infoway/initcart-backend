# pos/views/referral_lookup.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from users.models import User
from mlm.models.agent import Agent


class ReferralLookupAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        referral_code = request.GET.get("referral_code", "").strip()
        
        if not referral_code:
            return Response({
                "found": False,
                "message": "Referral code or mobile number required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = None
        agent = None
        
        # ── TRY 1: referral_code (UUID) se match ──────────────────────────
        try:
            user = User.objects.get(referral_code=referral_code)
            agent = Agent.objects.get(user=user, status="approved")
            print(f"✅ Found by referral_code: {referral_code} → {user.username}")
        except User.DoesNotExist:
            pass
        except Agent.DoesNotExist:
            user = None
        
        # ── TRY 2: Agent contact_number (mobile) se match ────────────────
        if not user:
            try:
                agent = Agent.objects.get(contact_number=referral_code)
                user = agent.user
                print(f"✅ Found by contact_number: {referral_code} → {user.username}")
            except Agent.DoesNotExist:
                pass
        
        # ── TRY 3: User phone field se match ──────────────────────────────
        if not user:
            try:
                user = User.objects.get(phone=referral_code)
                agent = Agent.objects.get(user=user, status="approved")
                print(f"✅ Found by phone: {referral_code} → {user.username}")
            except User.DoesNotExist:
                pass
            except Agent.DoesNotExist:
                user = None
        
        # ── TRY 4: Username se match (if username is phone) ──────────────
        if not user:
            try:
                user = User.objects.get(username=referral_code)
                agent = Agent.objects.get(user=user, status="approved")
                print(f"✅ Found by username: {referral_code} → {user.username}")
            except User.DoesNotExist:
                pass
            except Agent.DoesNotExist:
                user = None
        
        # ── Return result ──────────────────────────────────────────────────
        if user and agent and agent.status == "approved":
            return Response({
                "found": True,
                "agent_id": agent.id,
                "user_id": user.id,
                "full_name": agent.full_name,
                "contact_number": agent.contact_number,
                "agent_type": agent.agent_type,
                "referral_code": user.referral_code,
                "is_active": agent.is_active_agent,
                "username": user.username,
            })
        else:
            return Response({
                "found": False,
                "message": "Agent not found. Please check referral code or mobile number."
            })