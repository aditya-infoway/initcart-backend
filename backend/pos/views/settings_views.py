# pos/views/settings_views.py

from pos.models.purchasereturn import PurchaseReturnMaster
from pos.models.salesreturn import SalesReturnMaster
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import datetime

from pos.models.sales_bill_display_setting import SalesBillDisplaySetting
from pos.serializers.sales_bill_display_serializers import SalesBillDisplaySettingSerializer

from pos.models.settings import setting
from pos.models.bankpayment import BankPayment
from pos.models.bankreceipt import BankReceipt
from pos.models.cashpayment import CashPayment
from pos.models.cashreceipt import CashReceipt
from pos.models.purchaseentry import PurchaseMaster
from pos.models.salesentry import SalesMaster
from pos.models.contra import Contra
from pos.models.journalentries import JournalMaster
from pos.serializers.settings_serializers import SettingSerializers

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee


def ensure_branch_setting(branch):
    """Ensure that a branch has settings, create if not exists"""
    obj = setting.objects.filter(branch=branch).first()
    if not obj:
        obj = setting.objects.create(
            branch=branch,
            BP="BP",
            CP="CP",
            CR="CR",
            BR="BR",
            PI="PI",
            SI="SI",
            SR="SR",
            PR="PR",
            JE="JE",
            contra="CT",
        )
    return obj


# ─────────────────────────────────────────────────────────────────────────────
# SETTING VIEWS (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class SettingUpdateView(APIView):
    """Update branch settings"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Setting"  # ✅ ADD: Frontend route

    def get_branch(self, user):
        # ✅ CHANGE: getattr(user, "branch", None) → get_effective_branch()
        return user.get_effective_branch()

    def get_user_setting(self, user):
        branch = self.get_branch(user)
        if not branch:
            return None
        return ensure_branch_setting(branch)

    def get(self, request):
        user_setting = self.get_user_setting(request.user)
        if not user_setting:
            return Response(
                {"detail": "No settings found for this branch."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SettingSerializers(user_setting)
        return Response(serializer.data)

    def patch(self, request):
        # ✅ CHANGE: get_branch() → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        user_setting = self.get_user_setting(request.user)
        if not user_setting:
            return Response(
                {"detail": "No settings found for this branch."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SettingSerializers(
            user_setting,
            data=request.data,
            partial=True,
            context={"branch": branch},
        )

        if serializer.is_valid():
            serializer.save(branch=branch)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TaxApplyUpdateView(APIView):
    """Update GST toggle for purchase"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Setting"  # ✅ ADD: Frontend route
    
    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        obj = setting.objects.filter(branch=branch).first()
        return Response({
            "gst_toggle": int(obj.gst_toggle) if obj else 0
        })

    def patch(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        obj = ensure_branch_setting(branch)

        gst_toggle = request.data.get("gst_toggle")
        
        if isinstance(gst_toggle, str):
            gst_toggle = gst_toggle.lower() in ["true", "1", "yes", "on"]
        if gst_toggle is not None:
            obj.gst_toggle = bool(gst_toggle)
            obj.save()

        return Response({
            "gst_toggle": obj.gst_toggle
        })


class SalesTaxApplyUpdateView(APIView):
    """Update GST toggle for sales"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Setting"  # ✅ ADD: Frontend route

    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        obj = setting.objects.filter(branch=branch).first()
        return Response({
            "sales_gst_toggle": int(obj.sales_gst_toggle) if obj else 1
        })

    def patch(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        obj = ensure_branch_setting(branch)
        sales_gst_toggle = request.data.get("sales_gst_toggle")
        
        if isinstance(sales_gst_toggle, str):
            sales_gst_toggle = sales_gst_toggle.lower() in ["true", "1", "yes", "on"]
        if sales_gst_toggle is not None:
            obj.sales_gst_toggle = bool(sales_gst_toggle)
            obj.save()
            
        return Response({"sales_gst_toggle": obj.sales_gst_toggle})


class SettingCreateView(APIView):
    """Create branch settings"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Setting"  # ✅ ADD: Frontend route

    def get_branch(self, user):
        # ✅ CHANGE: getattr(user, "branch", None) → get_effective_branch()
        return user.get_effective_branch()

    def get_user_setting(self, user):
        branch = self.get_branch(user)
        if not branch:
            return None
        return ensure_branch_setting(branch)

    def get(self, request):
        user_setting = self.get_user_setting(request.user)
        if not user_setting:
            return Response(
                {"detail": "No settings found for this branch."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SettingSerializers(user_setting)
        return Response(serializer.data)

    def post(self, request):
        # ✅ CHANGE: get_branch() → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = SettingSerializers(
            data=request.data,
            context={"branch": branch},
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# VOUCHER GENERATOR — Helper API (No page_key, only IsAuthenticated)
# ─────────────────────────────────────────────────────────────────────────────

class GenerateVoucherView(APIView):
    """Generate voucher number for any module"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def get(self, request):
        voucher_type = request.GET.get("type")
        
        if not voucher_type:
            return Response(
                {"error": "Voucher type required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Map voucher types to their models and field names
        voucher_mapping = {
            'BP': (BankPayment, 'BP', 'voucher_no'),
            'CP': (CashPayment, 'CP', 'voucher_no'),
            'BR': (BankReceipt, 'BR', 'voucher_no'),
            'CR': (CashReceipt, 'CR', 'voucher_no'),
            'PI': (PurchaseMaster, 'PI', 'billNo'),
            'SI': (SalesMaster, 'SI', 'bill_no'),
            'PR': (PurchaseReturnMaster, 'PR', 'return_no'),
            'SR': (SalesReturnMaster, 'SR', 'return_no'),
            'CT': (Contra, 'contra', 'voucher_no'),
            'JE': (JournalMaster, 'JE', 'voucher_no'),
        }
        
        if voucher_type not in voucher_mapping:
            return Response(
                {"error": f"Invalid voucher type: {voucher_type}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        model_class, prefix_field, voucher_field = voucher_mapping[voucher_type]
        
        # Fetch prefix from settings
        settings_obj = setting.objects.filter(branch=branch).first()
        if not settings_obj:
            return Response(
                {"error": "Settings not found for this branch."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        prefix = getattr(settings_obj, prefix_field, prefix_field)
        
        # Calculate financial year
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year
        
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        
        # Filter by prefix AND financial year pattern
        pattern = f"{prefix}/{fy}/"
        
        # Build the filter based on the model's voucher field name
        filter_kwargs = {
            'branch': branch,
            f'{voucher_field}__startswith': pattern
        }
        
        # Get the last voucher with matching prefix and financial year
        last_voucher = model_class.objects.filter(
            **filter_kwargs
        ).order_by("-id").first()
        
        last_no = 0
        if last_voucher:
            val = getattr(last_voucher, voucher_field, None)
            if val:
                try:
                    parts = val.split("/")
                    if len(parts) >= 3:
                        last_no = int(parts[-1])
                except (ValueError, IndexError):
                    last_no = 0
        
        # Generate next voucher number
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{prefix}/{fy}/{next_no}"
        
        return Response({
            "voucher_no": voucher_no,
            "prefix": prefix,
            "financial_year": fy,
            "last_number": last_no,
            "next_number": last_no + 1,
            "voucher_type": voucher_type
        })


# ─────────────────────────────────────────────────────────────────────────────
# STOCK TRANSFER GST TOGGLE
# ─────────────────────────────────────────────────────────────────────────────

class StockTransferTaxApplyUpdateView(APIView):
    """Stock Transfer / Order Tracking GST toggle"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/Setting"  # ✅ ADD: Frontend route

    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        obj = setting.objects.filter(branch=branch).first()
        return Response({
            "stock_transfer_gst_toggle": int(obj.stock_transfer_gst_toggle) if obj else 0
        })

    def patch(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                "success": False,
                "error": "No branch linked to this user"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        obj = ensure_branch_setting(branch)
        value = request.data.get("stock_transfer_gst_toggle")
        
        if isinstance(value, str):
            value = value.lower() in ["true", "1", "yes", "on"]
        if value is not None:
            obj.stock_transfer_gst_toggle = bool(value)
            obj.save()
            
        return Response({"stock_transfer_gst_toggle": obj.stock_transfer_gst_toggle})


# ─────────────────────────────────────────────────────────────────────────────
# SALES BILL DISPLAY SETTING
# ─────────────────────────────────────────────────────────────────────────────

class SalesBillDisplaySettingView(APIView):
    """
    GET  -> sabhi authenticated users dekh sakte (read-only)
    PATCH -> sirf superadmin update kar sakta hai
    """
    
    # ✅ KEEP: IsAuthenticated (no page_key needed for this global setting)
    # PATCH permission manually checked below
    permission_classes = [IsAuthenticated]

    def get(self, request):
        obj = SalesBillDisplaySetting.get_solo()
        serializer = SalesBillDisplaySettingSerializer(obj)
        return Response(serializer.data)

    def patch(self, request):
        if getattr(request.user, "role", None) != "superadmin":
            return Response(
                {"error": "Only superadmin can update this setting"},
                status=status.HTTP_403_FORBIDDEN,
            )

        obj = SalesBillDisplaySetting.get_solo()
        serializer = SalesBillDisplaySettingSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)