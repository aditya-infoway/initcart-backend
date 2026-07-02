#mlm/views/agent_views.py
from rest_framework import generics
from rest_framework.permissions import AllowAny
from users.utils.permissions import IsSuperAdmin
from mlm.models.agent import Agent
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from mlm.serializers.agent_serializer import AgentRegistrationSerializer, AgentUpdateSerializer
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from users.models import User
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from rest_framework.parsers import MultiPartParser, FormParser , JSONParser
from rest_framework.generics import UpdateAPIView

class AgentRegisterView(generics.CreateAPIView):
    serializer_class = AgentRegistrationSerializer
    permission_classes = [AllowAny]


class AgentListView(generics.ListAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    queryset = Agent.objects.all().order_by('-created_at')
    serializer_class = AgentRegistrationSerializer


class AgentApproveView(generics.UpdateAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]
    queryset = Agent.objects.all().order_by('-created_at')
    serializer_class = AgentRegistrationSerializer
    lookup_field = "id"

    def perform_update(self, serializer):
        serializer.save(status="approved")
        


class AgentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Agent.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return AgentUpdateSerializer 
        return AgentRegistrationSerializer
    
# mlm/views/agent_views.py - Update AgentLoginView

class AgentLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username_or_phone = request.data.get("username", "").strip()
        password = request.data.get("password", "").strip()

        print(f"🔐 ===== AGENT LOGIN ATTEMPT =====")
        print(f"  Input: '{username_or_phone}'")
        print(f"  Password length: {len(password)}")

        if not username_or_phone or not password:
            return Response(
                {"error": "Username/Phone and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = None

        # ── TRY 1: Direct authenticate with username ──────────────────────
        try:
            user = authenticate(username=username_or_phone, password=password)
            if user:
                print(f"  ✅ Auth success: {user.username} (by username)")
        except Exception as e:
            print(f"  Auth error: {e}")

        # ── TRY 2: Agent contact_number se find ──────────────────────────
        if not user:
            try:
                agent = Agent.objects.filter(contact_number=username_or_phone).first()
                if agent:
                    print(f"  Found agent: {agent.full_name} (user: {agent.user.username})")
                    user = authenticate(username=agent.user.username, password=password)
                    if user:
                        print(f"  ✅ Auth success: {user.username} (by agent contact)")
            except Exception as e:
                print(f"  Agent lookup error: {e}")

        # ── TRY 3: User phone field se ────────────────────────────────────
        if not user:
            try:
                user_obj = User.objects.filter(phone=username_or_phone).first()
                if user_obj:
                    print(f"  Found user by phone: {user_obj.username}")
                    user = authenticate(username=user_obj.username, password=password)
                    if user:
                        print(f"  ✅ Auth success: {user.username} (by phone field)")
            except Exception as e:
                print(f"  Phone lookup error: {e}")

        # ── TRY 4: User email se ──────────────────────────────────────────
        if not user:
            try:
                user_obj = User.objects.filter(email=username_or_phone).first()
                if user_obj:
                    print(f"  Found user by email: {user_obj.username}")
                    user = authenticate(username=user_obj.username, password=password)
                    if user:
                        print(f"  ✅ Auth success: {user.username} (by email)")
            except Exception as e:
                print(f"  Email lookup error: {e}")

        # ── TRY 5: Username contains @, try email ────────────────────────
        if not user and "@" in username_or_phone:
            try:
                user_obj = User.objects.filter(username=username_or_phone).first()
                if user_obj:
                    print(f"  Found user by username: {user_obj.username}")
                    user = authenticate(username=user_obj.username, password=password)
                    if user:
                        print(f"  ✅ Auth success: {user.username} (by username with @)")
            except Exception as e:
                print(f"  Username lookup error: {e}")

        if not user:
            print(f"  ❌ AUTH FAILED for: {username_or_phone}")
            return Response(
                {"error": "Invalid credentials. Please check your mobile number and password."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── Refresh user ──────────────────────────────────────────────────
        user.refresh_from_db()
        print(f"  User: {user.username}, role: {user.role}, phone: {user.phone}")

        # ── Check if user is agent ────────────────────────────────────────
        if not user.is_agent():
            if user.is_branch() and Agent.objects.filter(user=user).exists():
                user.upgrade_role("agent")
                user.refresh_from_db()
                print(f"  ✅ Upgraded branch user to agent: {user.username}")
            else:
                print(f"  ❌ User is not an agent: {user.role}")
                return Response(
                    {"error": "Only agents can login here. Please register as an agent first."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # ── Check Agent exists ────────────────────────────────────────────
        try:
            agent = Agent.objects.get(user=user)
            print(f"  Agent found: {agent.full_name} (type: {agent.agent_type}, status: {agent.status})")
        except Agent.DoesNotExist:
            print(f"  ❌ Agent profile not found for user: {user.username}")
            return Response(
                {"error": "Agent profile not found. Please contact support."},
                status=status.HTTP_404_NOT_FOUND
            )

        # ── Check status ──────────────────────────────────────────────────
        if agent.agent_type != "pos":
            if agent.status == 'pending':
                return Response(
                    {"error": "Your agent application is pending approval. Please wait for admin approval."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if agent.status == 'rejected':
                return Response(
                    {"error": "Your agent application was rejected. Please contact support."},
                    status=status.HTTP_403_FORBIDDEN
                )
            if agent.status != "approved":
                return Response(
                    {"error": "Agent not approved yet. Please wait for admin approval."},
                    status=status.HTTP_403_FORBIDDEN
                )

        # ── Generate tokens ───────────────────────────────────────────────
        refresh = RefreshToken.for_user(user)
        referral_link = f"https://initcart.in/becomeAgent?ref={user.referral_code}"

        print(f"  ✅ LOGIN SUCCESS: {user.username}")
        print(f"  =====================================")

        return Response({
            "message": "Login successful",
            "user": {
                "id": user.id,
                "username": user.username,
                "phone": user.phone or agent.contact_number,
                "email": user.email,
                "referral_code": user.referral_code,
                "referral_link": referral_link,
                "user_type": user.user_type,
                "role": user.role,
                "agent_type": agent.agent_type,
                "full_name": agent.full_name,
                "contact_number": agent.contact_number,
                "is_active_agent": agent.is_active_agent,
                "status": agent.status,
            },
            "tokens": {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        })

class AgentUpdateView(generics.UpdateAPIView):
    """
    Update agent basic info (accepts JSON)
    """
    queryset = Agent.objects.all()
    serializer_class = AgentRegistrationSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]  # Only accept JSON

class AgentDocumentUploadView(generics.UpdateAPIView):
    """
    Upload agent documents (accepts multipart/form-data)
    """
    queryset = Agent.objects.all()
    serializer_class = AgentRegistrationSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def update(self, request, *args, **kwargs):
        agent = self.get_object()
        # Handle file uploads
        for field in ['passport_photo', 'id_proof', 'gst_certificate', 'business_license']:
            if field in request.FILES:
                setattr(agent, field, request.FILES[field])
        agent.save()
        return Response({'message': 'Documents updated successfully'}, status=status.HTTP_200_OK)

class AgentProfileView(APIView):
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        try:
            agent = Agent.objects.get(user=request.user)
            serializer = AgentRegistrationSerializer(agent)
 
            from mlm.models.mlm_settings import MLMSettings
            settings_obj   = MLMSettings.objects.first()
            min_sale_amount = float(settings_obj.minimum_sale_amount) if settings_obj else 0
 
            current_sales = float(agent.total_sales)
 
            # ✅ Branch signal se bana POS agent → already eligible
            if agent.agent_type == "pos" and agent.is_pos_branch_agent:
                has_minimum_sales  = True
                remaining          = 0
                shown_min_amount   = 0
                can_refer          = True
                refer_reason       = "POS Branch Agent — always eligible"
            else:
                # Manual POS / Normal / Society → normal check
                has_minimum_sales  = current_sales >= min_sale_amount
                remaining          = max(0, min_sale_amount - current_sales)
                shown_min_amount   = min_sale_amount
                
                # ✅ is_active_agent ko bhi check karo
                if agent.status == "approved" and agent.is_active_agent and has_minimum_sales:
                    can_refer = True
                    refer_reason = "Eligible to refer agents"
                else:
                    can_refer = False
                    if not agent.is_active_agent:
                        refer_reason = "Agent is not active"
                    elif not has_minimum_sales:
                        refer_reason = f"Need ₹{remaining:.0f} more in sales"
                    else:
                        refer_reason = "Agent not approved"
 
            data = serializer.data
            data['referral_link']      = f"https://initcart.in/becomeAgent?ref={request.user.referral_code}"
            data['sale_referral_link'] = f"https://initcart.in/?ref={request.user.referral_code}"
 
            data['can_refer_agents']        = can_refer
            data['has_minimum_sales']       = has_minimum_sales
            data['minimum_sale_amount']     = shown_min_amount
            data['current_total_sales']     = current_sales
            data['remaining_sales_needed']  = remaining
            data['is_pos_branch_agent']     = agent.is_pos_branch_agent
            if agent.minimum_achieved_order:
                data['minimum_achieved_order'] = {
                    'id': agent.minimum_achieved_order.id,
                    'order_number': agent.minimum_achieved_order.order_number,
                    'order_amount': float(agent.minimum_achieved_order.final_amount),  # full order amount
                    'created_at': str(agent.minimum_achieved_order.created_at),
                }
            else:
                data['minimum_achieved_order'] = None
            data['is_active_agent']         = agent.is_active_agent  # ✅ Add this
 
            # Active status reason
            if agent.agent_type == "pos" and agent.is_pos_branch_agent:
                active_reason = "POS Branch Agent — Always Active"
            elif agent.status == "pending":
                active_reason = "Pending admin approval"
            elif not has_minimum_sales:
                active_reason = f"Need ₹{remaining:.0f} more in sales"
            elif not agent.is_active_agent:
                active_reason = "Agent not active"
            else:
                active_reason = "Active"
 
            data['agent_active_status'] = {
                'is_active'          : agent.is_active_agent,
                'status'             : agent.status,
                'agent_type'         : agent.agent_type,
                'is_pos_branch_agent': agent.is_pos_branch_agent,
                'reason'             : active_reason,
            }
 
            # Sponsor info
            if request.user.referred_by:
                sponsor = request.user.referred_by
                try:
                    sponsor_name = sponsor.agent.full_name
                except Exception:
                    sponsor_name = None
                data['sponsor'] = {
                    'id'           : sponsor.id,
                    'username'     : sponsor.username,
                    'full_name'    : sponsor_name,
                    'referral_code': sponsor.referral_code,
                }
            else:
                data['sponsor'] = None
 
            return Response(data)
 
        except Agent.DoesNotExist:
            return Response(
                {"error": "Agent profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )
 
        