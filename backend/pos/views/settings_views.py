#pos/views/settings_views.py
from pos.models.purchasereturn import PurchaseReturnMaster
from pos.models.salesreturn import SalesReturnMaster
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import datetime  # correct

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
class SettingUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        return getattr(user, "branch", None)

    def get_user_setting(self, user):
        return ensure_branch_setting(user.branch)


    # GET: fetch current setting
    def get(self, request):
        user_setting = self.get_user_setting(request.user)
        if not user_setting:
            return Response(
                {"detail": "No settings found for this branch."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = SettingSerializers(user_setting)
        return Response(serializer.data)

    # PATCH: update only entered fields
    def patch(self, request):
        branch = self.get_branch(request.user)
        if not branch:
            return Response(
                {"detail": "User does not have a branch assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_setting = self.get_user_setting(request.user)
        if not user_setting:
            return Response(
                {"detail": "No settings found for this branch."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = SettingSerializers(
            user_setting,
            data=request.data,
            partial=True,  # only update provided fields
            context={"branch": branch},
        )

        if serializer.is_valid():
            serializer.save(branch=branch)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class TaxApplyUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        obj = setting.objects.filter(branch=request.user.branch).first()

        return Response({
            "gst_toggle": int(obj.gst_toggle) if obj else 0
        })

    def patch(self, request):
        # get or create setting for branch
        obj = ensure_branch_setting(request.user.branch)

        # 🔥 direct store (1 / 0 / true / false)
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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        obj = setting.objects.filter(branch=request.user.branch).first()
        return Response({
            "sales_gst_toggle": int(obj.sales_gst_toggle) if obj else 1
        })

    def patch(self, request):
        obj = ensure_branch_setting(request.user.branch)
        sales_gst_toggle = request.data.get("sales_gst_toggle")
        if isinstance(sales_gst_toggle, str):
            sales_gst_toggle = sales_gst_toggle.lower() in ["true", "1", "yes", "on"]
        if sales_gst_toggle is not None:
            obj.sales_gst_toggle = bool(sales_gst_toggle)
            obj.save()
        return Response({"sales_gst_toggle": obj.sales_gst_toggle})
    
class SettingCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch(self, user):
        """Return branch assigned to the user"""
        return getattr(user, "branch", None)

    def get_user_setting(self, user):
        return ensure_branch_setting(user.branch)


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
        branch = self.get_branch(request.user)

        if not branch:
            return Response(
                {"detail": "User does not have a branch assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SettingSerializers(
            data=request.data,
            context={"branch": branch},
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GenerateVoucherView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def get(self, request):
        voucher_type = request.GET.get("type")  # BP, CP, etc.
        
        if not voucher_type:
            return Response(
                {"error": "Voucher type required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Map voucher types to their models and field names
        voucher_mapping = {
            'BP': (BankPayment, 'BP', 'voucher_no'),  # (model, prefix_field, voucher_field)
            'CP': (CashPayment, 'CP', 'voucher_no'),
            'BR': (BankReceipt, 'BR', 'voucher_no'),
            'CR': (CashReceipt, 'CR', 'voucher_no'),
            'PI': (PurchaseMaster, 'PI', 'billNo'),  # Purchase uses billNo
            'SI': (SalesMaster, 'SI', 'bill_no'),    # Sales uses bill_no
            'PR': (PurchaseReturnMaster, 'PR', 'return_no'),  # Purchase Return
            'SR': (SalesReturnMaster, 'SR', 'return_no'),     # Sales Return
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
        settings_obj = setting.objects.filter(branch=request.user.branch).first()
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
            'branch': request.user.branch,
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
        



class StockTransferTaxApplyUpdateView(APIView):
    """Stock Transfer / Order Tracking GST toggle — Purchase/Sales toggle jaisa hi."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        obj = setting.objects.filter(branch=request.user.branch).first()
        return Response({
            "stock_transfer_gst_toggle": int(obj.stock_transfer_gst_toggle) if obj else 0
        })

    def patch(self, request):
        obj = ensure_branch_setting(request.user.branch)
        value = request.data.get("stock_transfer_gst_toggle")
        if isinstance(value, str):
            value = value.lower() in ["true", "1", "yes", "on"]
        if value is not None:
            obj.stock_transfer_gst_toggle = bool(value)
            obj.save()
        return Response({"stock_transfer_gst_toggle": obj.stock_transfer_gst_toggle})        
        