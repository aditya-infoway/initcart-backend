# pos/views/branch_views.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from django.contrib.auth.hashers import check_password
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import authenticate
from django.db import models
from django.contrib.auth import get_user_model

from pos.models.settings import setting
from pos.views.settings_views import ensure_branch_setting


# Models
from pos.models.branch import Branch

# Serializers
from pos.serializers.branch_serializers import (
    BranchCreateSerializer, BranchListSerializer, 
    BranchDetailSerializer, BranchUpdateSerializer
)

# Permissions
from ecommerce.permissions import IsSuperAdmin

User = get_user_model()

#  BRANCH VIEWSET (CRUD + Admin Create)


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]  # Only Super Admin can access
    parser_classes = [MultiPartParser, FormParser]
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["branch_name", "owner_name", "email", "phone", "city", "state"]
    filterset_fields = ["branch_type", "status"]

    def get_serializer_class(self):
        if self.action == "create":
            return BranchCreateSerializer
        elif self.action == "list":
            return BranchListSerializer
        elif self.action in ["retrieve", "me"]:
            return BranchDetailSerializer
        elif self.action in ["update", "partial_update"]:
            return BranchUpdateSerializer
        return BranchDetailSerializer

    # Create Branch (Admin Only) 
    def create(self, request, *args, **kwargs):
        data = request.data.copy()

        password = data.get("password")

        if not password:
            return Response({"error": "Password is required"}, status=400)

        serializer = BranchCreateSerializer(data=data)

        if serializer.is_valid():
            branch = serializer.save()

            return Response({
                "success": True,
                "message": "Branch created successfully!",
                "branch": BranchDetailSerializer(branch).data
            }, status=201)

        return Response(serializer.errors, status=400)

    #List Branches 
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "success": True,
                "data": serializer.data,
                "count": queryset.count()
            })
        
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "data": serializer.data,
            "count": queryset.count()
        })

    #  Retrieve Branch
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "data": serializer.data
        })

    def destroy(self, request, *args, **kwargs):
          try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({
                "success": True,
                "message": "Branch deleted successfully"
            }, status=status.HTTP_200_OK)
          except Exception as e:
            return Response({
                "success": False,
                "message": str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    #  Update Branch
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Branch updated successfully!",
                "data": serializer.data
            })
        return Response({
            "success": False,
            "errors": serializer.errors
        }, status=400)
    
    # Change Status 
    @action(detail=True, methods=['post'])
    def change_status(self, request, pk=None):
        branch = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in ['active', 'inactive']:
            return Response({
                'success': False,
                'message': 'Invalid status value. Use "active" or "inactive"'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        branch.status = new_status
        branch.save()
        
        return Response({
            'success': True,
            'message': f'Branch status changed to {new_status}',
            'data': BranchListSerializer(branch).data
        })

    #  Get Branch Stats 
    @action(detail=False, methods=['get'])
    def stats(self, request):
        total = Branch.objects.count()
        active = Branch.objects.filter(status='active').count()
        inactive = Branch.objects.filter(status='inactive').count()
        
        by_type = Branch.objects.values('branch_type').annotate(count=models.Count('id'))
        
        return Response({
            'success': True,
            'data': {
                'total': total,
                'active': active,
                'inactive': inactive,
                'by_type': by_type
            }
        })

#  BRANCH LOGIN     
from django.utils import timezone
from datetime import timedelta
@method_decorator(csrf_exempt, name="dispatch")
# pos/views/branch_views.py - UPDATE BranchLoginViewset

# pos/views/branch_views.py - Update BranchLoginViewset

class BranchLoginViewset(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        identifier = request.data.get("identifier", "").strip()
        password = request.data.get("password", "").strip()

        if not identifier or not password:
            return Response(
                {"success": False, "message": "Email/Phone & Password required"},
                status=400,
            )

        #  STEP 1: Check for Super Admin
        try:
            user = User.objects.get(email=identifier)
            
            # Authenticate using django's authenticate
            auth_user = authenticate(username=user.username, password=password)
            
            if auth_user and auth_user.role == 'superadmin':
                #  AUTO-CREATE MAIN BRANCH IF NOT EXISTS (Sirf Super Admin ke liye)
                branch, created = Branch.objects.get_or_create(
                    user=auth_user,
                    defaults={
                        'branch_name': f"{auth_user.username}_Main_Branch",
                        'owner_name': auth_user.get_full_name() or "Super Admin",
                        'email': auth_user.email,
                        'phone': auth_user.phone or "0000000000",
                        'status': 'active',
                        'branch_type': 'fashion',
                        'address': 'Head Office',
                        'city': 'Main City',
                        'state': 'Main State'
                    }
                )
                
                refresh = RefreshToken.for_user(auth_user)
                
                branch_data = {
                    "id": branch.id,
                    "email": branch.email,
                    "branch_name": branch.branch_name,
                    "owner_name": branch.owner_name,
                    "branch_type": branch.branch_type,
                    "phone": branch.phone,
                    "status": branch.status,
                }
                
                return Response({
                    "success": True,
                    "message": "Super Admin login successful",
                    "branch": branch_data,
                    "user": {
                        "id": auth_user.id,
                        "username": auth_user.username,
                        "email": auth_user.email,
                        "role": auth_user.role,
                    },
                    "prefixes": {
                        "gst_toggle": False,
                        "PI": "PI", "SI": "SI", "BP": "BP",
                        "CP": "CP", "CR": "CR", "BR": "BR",
                        "JE": "JE", "contra": "CN",
                    },
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                })
        except User.DoesNotExist:
            pass  # Not a super admin

        #  STEP 2: Normal Branch Login (Existing code - No changes)
        branch = (
            Branch.objects.filter(email=identifier).first()
            or Branch.objects.filter(phone=identifier).first()
        )

        if not branch:
            return Response({"success": False, "message": "Branch not found"}, status=404)

        if not branch.user:
            return Response({
                "success": False, 
                "message": "Branch account not properly configured. No user associated."
            }, status=400)

        if branch.status != 'active':
            return Response({"success": False, "message": "Branch is not active"}, status=403)

        # Authenticate branch user
        user = authenticate(username=branch.user.username, password=password)
        
        if user is None:
            user = authenticate(username=branch.email, password=password)
        
        if user is None:
            return Response({"success": False, "message": "Invalid credentials"}, status=400)

        stale_time = timezone.now() - timedelta(seconds=1)

        if branch.is_logged_in and branch.last_active and branch.last_active > stale_time:
            return Response({
                "success": False,
                "message": "Already logged in on another device. Please logout first."
            }, status=403)

        if branch.is_logged_in and branch.last_active and branch.last_active <= stale_time:
            branch.is_logged_in = False
            branch.last_active = None
            branch.save(update_fields=["is_logged_in", "last_active"])

        branch.is_logged_in = True
        branch.last_active = timezone.now()
        branch.save(update_fields=["is_logged_in", "last_active"])
        
        prefixes = {
            "gst_toggle": False,
            "PI": "PI", "SI": "SI", "BP": "BP",
            "CP": "CP", "CR": "CR", "BR": "BR",
            "JE": "JE", "contra": "CN",
        }

        refresh = RefreshToken.for_user(user)

        return Response({
            "success": True,
            "message": "Login successful",
            "branch": {
                "id": branch.id,
                "email": branch.email,
                "branch_name": branch.branch_name,
                "owner_name": branch.owner_name,
                "branch_type": branch.branch_type,
                "phone": branch.phone,
                "status": branch.status,
            },
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
            },
            "prefixes": prefixes,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })
# ------------------------
# BRANCH LOGOUT
# ------------------------
import json
User = get_user_model()

# pos/views/branch_views.py - UPDATE BranchLogoutViewset

@method_decorator(csrf_exempt, name="dispatch")
class BranchLogoutViewset(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser]

    def post(self, request):
        user = None
        access_token_str = None
        refresh_token = None

        # --------------------------
        # Case 1 — Normal Axios logout
        # --------------------------
        if request.user and request.user.is_authenticated:
            user = request.user
            header = request.headers.get("Authorization")
            if header and header.startswith("Bearer "):
                access_token_str = header.split(" ")[1]

        # --------------------------
        # Case 2 — Beacon logout fallback
        # --------------------------
        if not user:
            try:
                data = request.data if isinstance(request.data, dict) else json.loads(request.body.decode("utf-8") or "{}")
                access_token_str = data.get("token")
                refresh_token = data.get("refresh")  #  Get refresh token

                if access_token_str:
                    token = AccessToken(access_token_str)
                    user = User.objects.get(id=token["user_id"])
            except Exception as e:
                print(" Token decode error:", e)

        if not user:
            return Response({"success": False, "message": "User not found"}, status=status.HTTP_401_UNAUTHORIZED)

        

        # -------------------------
        #  CRITICAL: Branch logout update - Reset is_logged_in
        # --------------------------
        try:
            branch = Branch.objects.get(user=user)
            branch.is_logged_in = False  #  Important: Reset this flag
            branch.last_active = None    #  Also reset last_active
            branch.save(update_fields=["is_logged_in", "last_active"])
            
        except Branch.DoesNotExist:
            return Response({"success": False, "message": "Branch not found"}, status=status.HTTP_404_NOT_FOUND)

        # --------------------------
        # Token blacklist
        # --------------------------
        try:
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
                
            else:
                # Try to get refresh token from request data
                data = request.data if isinstance(request.data, dict) else {}
                refresh_token = data.get("refresh")
                if refresh_token:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                    
        except Exception as e:
            print("Token blacklist error:", e)

        return Response({"success": True, "message": "Logged out successfully"}, status=status.HTTP_200_OK)
    
    def get(self, request):
        user = request.user

        if user.is_anonymous:
            return Response({"message": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            branch = Branch.objects.get(user=user)
            return Response({"is_logged_in": branch.is_logged_in}, status=status.HTTP_200_OK)
        except Branch.DoesNotExist:
            return Response({"message": "Branch not found"}, status=status.HTTP_404_NOT_FOUND)
        
# pos/views/branch_views.py - UPDATE BranchHeartbeatView

class BranchHeartbeatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            branch = Branch.objects.get(user=request.user)
            
            #  Update last_active time
            branch.last_active = timezone.now()
            
            #  If somehow is_logged_in is False, set it to True
            if not branch.is_logged_in:
                branch.is_logged_in = True
                
            branch.save(update_fields=["last_active", "is_logged_in"])
            print(f" Heartbeat received for branch: {branch.branch_name}")
            
        except Branch.DoesNotExist:
            
            return Response({"error": "Branch not found"}, status=404)
        except Exception as e:
            
            return Response({"error": str(e)}, status=500)

        return Response({"success": True, "message": "Heartbeat received"})


# pos/views/branch_views.py - Update BranchMeView

class BranchMeView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response(
                {"success": False, "message": "Branch profile not linked with this user"},
                status=404
            )
        serializer = BranchDetailSerializer(branch)
        return Response({"success": True, "data": serializer.data})

    def patch(self, request):
        """Branch updates its own limited profile"""
        try:
            branch = Branch.objects.get(user=request.user)
        except Branch.DoesNotExist:
            return Response(
                {"success": False, "message": "Branch profile not linked with this user"},
                status=404
            )

        # ✅ Allow more fields for superadmin
        allowed_fields = {
            "branch_code", "city", "state", "country", "address", 
            "phone", "owner_name", "bank_name", "account_number", 
            "ifsc_code", "upi_id"
        }
        data = {k: v for k, v in request.data.items() if k in allowed_fields}
        
        if not data:
            return Response(
                {"success": False, "message": "No editable fields provided."}, 
                status=400
            )

        serializer = BranchUpdateSerializer(branch, data=data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Profile updated successfully!",
                "data": BranchDetailSerializer(branch).data
            })
        return Response({"success": False, "errors": serializer.errors}, status=400)