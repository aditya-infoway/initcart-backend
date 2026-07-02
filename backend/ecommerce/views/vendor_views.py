from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth.hashers import check_password, make_password
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import SessionAuthentication

# MODELS
from ecommerce.models.vendor import (
    Vendor, VendorApprovalRequest, VendorWallet,
    VendorWithdrawalRequest, Brand
)

# SERIALIZERS
from ecommerce.serializers.vendor_serializers import (
    VendorRegistrationSerializer, VendorListSerializer, VendorDetailSerializer,
    VendorSerializer, VendorApprovalSerializer, VendorApprovalActionSerializer,
    VendorWalletSerializer, VendorWithdrawalSerializer, BrandSerializer
)

# PERMISSIONS
from ecommerce.permissions import IsSuperAdmin
from django.contrib.auth import get_user_model
User = get_user_model()


# =========================================================
#  🔹 VENDOR VIEWSET (Register + CRUD + Dashboard)
# =========================================================
class VendorViewSet(viewsets.ModelViewSet):
    queryset = Vendor.objects.all().order_by('-created_at')
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["business_name", "owner_name", "email", "phone"]
    filterset_fields = ["vendor_type", "status", "verification_label"]

    def get_serializer_class(self):
        if self.action == "register":
            return VendorRegistrationSerializer
        elif self.action in ["list", "product_vendors", "service_vendors"]:
            return VendorListSerializer
        return VendorDetailSerializer

    def get_permissions(self):
        if self.action == "register":
            return [AllowAny()]
        return [IsAuthenticated()]

    # ✅ UPDATE METHOD - For PUT requests
    def update(self, request, *args, **kwargs):
        """Handle PUT requests for full updates"""
        print("🔄 PUT request received for vendor update")
        return self._handle_update(request, *args, **kwargs)

    # ✅ PARTIAL UPDATE METHOD - For PATCH requests
    def partial_update(self, request, *args, **kwargs):
        """Handle PATCH requests for partial updates"""
        print("🔄 PATCH request received for vendor update")
        return self._handle_update(request, partial=True, *args, **kwargs)

    def _handle_update(self, request, partial=False, *args, **kwargs):
        """Common method to handle both PUT and PATCH updates"""
        vendor = self.get_object()
        
        print(f"Updating vendor: {vendor.id} - {vendor.email}")
        print("Request data:", request.data)
        print("Request files:", request.FILES)
        
        # Create a mutable copy of request data
        data = request.data.copy()
        
        # Handle password separately
        raw_password = data.get("password")
        password_updated = False
        
        if raw_password and raw_password.strip():
            print(f"🔑 Updating password for vendor: {vendor.email}")
            # Update Django user password
            if vendor.user:
                vendor.user.set_password(raw_password)
                vendor.user.save()
                print("✅ Django user password updated")
            # Update vendor password hash
            vendor.password = make_password(raw_password)
            password_updated = True
            print("✅ Vendor password hash updated")
        
        # Update other fields
        field_mapping = {
            'vendor_type': 'vendor_type',
            'vendor_subtype': 'vendor_subtype',
            'business_name': 'business_name',
            'owner_name': 'owner_name',
            'email': 'email',
            'phone': 'phone',
            'address': 'address',
            'city': 'city',
            'state': 'state',
            'pincode': 'pincode',
            'bank_name': 'bank_name',
            'account_number': 'account_number',
            'ifsc_code': 'ifsc_code',
            'upi_id': 'upi_id',
            'status': 'status',
        }
        
        updated_fields = []
        
        for frontend_field, model_field in field_mapping.items():
            if frontend_field in data:
                value = data[frontend_field]
                # For partial update, only update if value is provided
                if partial and value is None:
                    continue
                if value is not None and value != '':
                    # Convert status to lowercase for database
                    if model_field == 'status' and value:
                        value = value.lower()
                    setattr(vendor, model_field, value)
                    updated_fields.append(model_field)
                    print(f"  ✅ Updated {model_field}: {value}")
        
        # Handle file uploads
        file_fields = ['licence_file', 'gst_certificate', 'store_logo', 'id_proof']
        for file_field in file_fields:
            if file_field in request.FILES:
                setattr(vendor, file_field, request.FILES[file_field])
                updated_fields.append(file_field)
                print(f"  ✅ Updated file: {file_field}")
        
        # Save the vendor
        if updated_fields or password_updated:
            vendor.save()
            print(f"✅ Vendor {vendor.id} updated successfully")
            print(f"  - Fields updated: {updated_fields}")
            if password_updated:
                print(f"  - Password updated: Yes")
        
        # Refresh from database to get latest data
        vendor.refresh_from_db()
        
        return Response({
            "success": True,
            "message": "Vendor updated successfully!",
            "vendor": VendorDetailSerializer(vendor).data
        }, status=status.HTTP_200_OK)

    # Vendor Registration
    @action(detail=False, methods=["post"], permission_classes=[AllowAny])
    def register(self, request):
        data = request.data.copy()

        password = data.get("password")
        confirm_password = data.get("confirm_password")

        if not password or not confirm_password:
            return Response({"message": "Password & Confirm Password required"}, status=400)

        if password != confirm_password:
            return Response({"message": "Passwords do not match"}, status=400)

        serializer = VendorRegistrationSerializer(data=data)

        if serializer.is_valid():
            vendor = serializer.save()
            VendorApprovalRequest.objects.get_or_create(vendor=vendor)
            VendorWallet.objects.get_or_create(vendor=vendor)

            return Response({
                "success": True,
                "message": "Vendor registered! Awaiting admin approval.",
                "vendor_id": vendor.id,
                "status": vendor.status
            }, status=201)

        return Response(serializer.errors, status=400)

    # ✅ Admin Create/Update Vendor
    @action(detail=False, methods=["post"], permission_classes=[IsSuperAdmin], url_path="create_by_admin")
    def create_by_admin(self, request):
        print("=" * 50)
        print("create_by_admin called")
        print("Request method:", request.method)
        print("Files:", request.FILES)
        print("Data:", request.data)
        print("=" * 50)
        
        data = request.data.copy()
        
        # Check if this is an update (has 'id' field)
        vendor_id = data.get("id")
        
        if vendor_id:
            # ========== UPDATE EXISTING VENDOR ==========
            print(f"🔄 Updating vendor with ID: {vendor_id}")
            
            try:
                vendor = Vendor.objects.get(id=vendor_id)
                
                # Handle password update separately
                raw_password = data.get("password")
                password_updated = False
                
                if raw_password and raw_password.strip():
                    print(f"🔑 Updating password for vendor: {vendor.email}")
                    # Update Django user password
                    if vendor.user:
                        vendor.user.set_password(raw_password)
                        vendor.user.save()
                        print("✅ Django user password updated")
                    # Update vendor password hash
                    vendor.password = make_password(raw_password)
                    password_updated = True
                    print("✅ Vendor password hash updated")
                
                # Update other fields
                field_mapping = {
                    'vendor_type': 'vendor_type',
                    'vendor_subtype': 'vendor_subtype',
                    'business_name': 'business_name',
                    'owner_name': 'owner_name',
                    'email': 'email',
                    'phone': 'phone',
                    'address': 'address',
                    'city': 'city',
                    'state': 'state',
                    'pincode': 'pincode',
                    'bank_name': 'bank_name',
                    'account_number': 'account_number',
                    'ifsc_code': 'ifsc_code',
                    'upi_id': 'upi_id',
                    'status': 'status',
                }
                
                updated_fields = []
                
                for frontend_field, model_field in field_mapping.items():
                    if frontend_field in data:
                        value = data[frontend_field]
                        if value is not None and value != '':
                            # Convert status to lowercase for database
                            if model_field == 'status' and value:
                                value = value.lower()
                            setattr(vendor, model_field, value)
                            updated_fields.append(model_field)
                            print(f"  ✅ Updated {model_field}: {value}")
                
                # Handle file uploads
                file_fields = ['licence_file', 'gst_certificate', 'store_logo', 'id_proof']
                for file_field in file_fields:
                    if file_field in request.FILES:
                        setattr(vendor, file_field, request.FILES[file_field])
                        updated_fields.append(file_field)
                        print(f"  ✅ Updated file: {file_field}")
                
                # Save the vendor
                if updated_fields or password_updated:
                    vendor.save()
                    print(f"✅ Vendor {vendor.id} updated successfully")
                    print(f"  - Fields updated: {updated_fields}")
                    if password_updated:
                        print(f"  - Password updated: Yes")
                
                # Refresh vendor from database to get latest data
                vendor.refresh_from_db()
                
                return Response({
                    "success": True,
                    "message": "Vendor updated successfully!",
                    "vendor": VendorDetailSerializer(vendor).data
                }, status=status.HTTP_200_OK)
                
            except Vendor.DoesNotExist:
                print(f"❌ Vendor with ID {vendor_id} not found")
                return Response({"error": "Vendor not found"}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                print(f"❌ Error updating vendor: {str(e)}")
                import traceback
                traceback.print_exc()
                return Response({"error": f"Update failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        
        else:
            # ========== CREATE NEW VENDOR ==========
            print("➕ Creating new vendor")
            
            raw_password = data.get("password")
            if not raw_password:
                return Response({"error": "Password is required"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Create Django user
            try:
                user = User.objects.create_user(
                    username=data["email"],
                    email=data["email"],
                    password=raw_password,
                    role="vendor"
                )
                print(f"✅ Django user created: {user.email}")
            except Exception as e:
                print(f"❌ User creation failed: {str(e)}")
                return Response({"error": f"User creation failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Save vendor with hashed password
            data["password"] = make_password(raw_password)
            
            serializer = VendorSerializer(data=data)
            
            if serializer.is_valid():
                try:
                    vendor = serializer.save(
                        user=user,
                        created_by=request.user,
                        status="active",
                        is_approved=True,
                        verification_label="verified"
                    )
                    
                    VendorWallet.objects.get_or_create(vendor=vendor)
                    print(f"✅ New vendor created with ID: {vendor.id}")
                    
                    return Response({
                        "success": True,
                        "message": "Vendor created by admin!",
                        "vendor": VendorDetailSerializer(vendor).data
                    }, status=status.HTTP_201_CREATED)
                except Exception as e:
                    print(f"❌ Vendor save failed: {str(e)}")
                    return Response({"error": f"Vendor save failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
            
            print("❌ Serializer validation failed:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Product Vendors
    @action(detail=False, methods=["get"], permission_classes=[IsSuperAdmin])
    def product_vendors(self, request):
        vendors = self.queryset.filter(vendor_type="product", status="active")
        return Response(VendorListSerializer(vendors, many=True).data)

    # Service Vendors
    @action(detail=False, methods=["get"], permission_classes=[IsSuperAdmin])
    def service_vendors(self, request):
        vendors = self.queryset.filter(vendor_type="service", status="active")
        return Response(VendorListSerializer(vendors, many=True).data)

    # Vendor Dashboard 
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def dashboard(self, request):
        vendor = get_object_or_404(Vendor, user=request.user)
        wallet = VendorWallet.objects.get(vendor=vendor)

        return Response({
            "vendor": VendorDetailSerializer(vendor).data,
            "wallet": VendorWalletSerializer(wallet).data,
        })


#  🔹 VENDOR LOGIN
@method_decorator(csrf_exempt, name="dispatch")
class VendorLoginViewset(APIView):
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

        vendor = (
            Vendor.objects.filter(email=identifier).first()
            or Vendor.objects.filter(phone=identifier).first()
        )

        if not vendor:
            return Response({"success": False, "message": "Vendor not found"}, status=404)
        
        if vendor.vendor_type != "product":
            return Response({"success": False, "message": "Only product vendors can login here"},
            status=403)

        if not check_password(password, vendor.password):
            return Response({"success": False, "message": "Invalid credentials"}, status=400)

        if not vendor.is_approved:
            return Response({"success": False, "message": "Pending approval"}, status=403)

        user = vendor.user
        refresh = RefreshToken.for_user(user)

        return Response({
            "success": True,
            "message": "Login successful",
            "vendor": {
                "id": vendor.id,
                "email": vendor.email,
                "business_name": vendor.business_name,
                "is_approved": vendor.is_approved,
                "status": vendor.status,
            },
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })


#  🔹 SERVICE VENDOR LOGIN
@method_decorator(csrf_exempt, name="dispatch")
class ServiceVendorLoginViewset(APIView):
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

        vendor = (
            Vendor.objects.filter(email=identifier).first()
            or Vendor.objects.filter(phone=identifier).first()
        )

        if not vendor:
            return Response({"success": False, "message": "Vendor not found"}, status=404)
        
        if vendor.vendor_type != "service":
            return Response({"success": False, "message": "Only Service vendors can login here"},
            status=403)

        if not check_password(password, vendor.password):
            return Response({"success": False, "message": "Invalid credentials"}, status=400)

        if not vendor.is_approved:
            return Response({"success": False, "message": "Pending approval"}, status=403)

        user = vendor.user
        refresh = RefreshToken.for_user(user)

        return Response({
            "success": True,
            "message": "Login successful",
            "vendor": {
                "id": vendor.id,
                "email": vendor.email,
                "business_name": vendor.business_name,
                "is_approved": vendor.is_approved,
                "status": vendor.status,
                "vendor_type": vendor.vendor_type,
                "vendor_subtype": vendor.vendor_subtype, 
                "owner_name": vendor.owner_name,  
                "phone": vendor.phone, 
            },
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })
        
#  🔹 VENDOR APPROVAL VIEWSET
class VendorApprovalViewSet(viewsets.ModelViewSet):
    queryset = VendorApprovalRequest.objects.all().order_by('-date')
    serializer_class = VendorApprovalSerializer
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    @action(detail=False, methods=["get"])
    def pending(self, request):
        pending = self.queryset.filter(status="pending")
        return Response({
            "count": pending.count(),
            "approval_requests": VendorApprovalSerializer(pending, many=True).data
        })

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        approval = self.get_object()
        serializer = VendorApprovalActionSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        vendor = approval.vendor
        data = serializer.validated_data

        vendor.bank_name = data["bank_name"]
        vendor.account_number = data["account_number"]
        vendor.ifsc_code = data["ifsc_code"]
        vendor.upi_id = data.get("upi_id", "")
        vendor.status = "active"
        vendor.verification_label = "verified"
        vendor.is_approved = True
        vendor.save()

        approval.status = "approved"
        approval.admin_notes = data.get("admin_notes", "")
        approval.save()

        return Response({"message": "Vendor approved!"})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        approval = self.get_object()
        vendor = approval.vendor

        vendor.status = "rejected"
        vendor.verification_label = "rejected"
        vendor.save()

        approval.status = "rejected"
        approval.admin_notes = request.data.get("admin_notes", "")
        approval.save()

        return Response({"message": "Vendor rejected!"})


# =========================================================
#  🔹 WALLET / WITHDRAWAL / BRAND
# =========================================================
class VendorWalletViewSet(viewsets.ModelViewSet):
    queryset = VendorWallet.objects.all().order_by('-updated_at')
    serializer_class = VendorWalletSerializer
    permission_classes = [IsSuperAdmin]


class VendorWithdrawalViewSet(viewsets.ModelViewSet):
    queryset = VendorWithdrawalRequest.objects.all().order_by('-request_date')
    serializer_class = VendorWithdrawalSerializer
    permission_classes = [IsSuperAdmin]

    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):
        withdrawal = self.get_object()
        status_value = request.data.get("status")

        if status_value not in ["approved", "rejected", "paid"]:
            return Response({"error": "Invalid status"}, status=400)

        withdrawal.status = status_value
        if status_value == "paid":
            withdrawal.paid_date = timezone.now()

        withdrawal.save()
        return Response({"message": f"Status updated to {status_value}"})


class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all().order_by("brand_name")
    serializer_class = BrandSerializer
    parser_classes = [MultiPartParser, FormParser]  # ✅ For file uploads

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsSuperAdmin()]
        else:
            return [IsSuperAdmin()]


# =========================================================
#  🔹 Vendor Me (Profile)
# =========================================================
class VendorMeView(APIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            vendor = Vendor.objects.get(user=request.user)
            serializer = VendorDetailSerializer(vendor)
            return Response({
                "success": True,
                "data": serializer.data
            })
        except Vendor.DoesNotExist:
            return Response(
                {"success": False, "message": "Vendor profile not linked with this user"},
                status=404
            )