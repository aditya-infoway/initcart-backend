# salesentry_views.py 


from datetime import datetime
from pos.models.bankpayment import BankPayment
from pos.models.cashpayment import CashPayment
from pos.models.purchaseentry import PurchaseItem
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Sum
from django.db import transaction
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from pos.models.salesentry import SalesItem, SalesMaster
from pos.models.branch import Branch
from pos.models.items import items, itemvariants
from pos.serializers.salesentry_serializers import SalesMasterSerializer
from pos.models.account import Account
from pos.models.cashreceipt import CashReceipt
from pos.models.bankreceipt import BankReceipt
from rest_framework.decorators import api_view
from pos.models.settings import setting
from pos.utils.pagination import StandardResultsSetPagination
from django.db.utils import IntegrityError
import time
from pos.utils.sales_bill_display import get_display_branch_for_sale

def calculate_gst(taxable, tax_percent, branch_state, party_state):
    """
    Calculates CGST, SGST, IGST, and total tax.
    Tax-free if tax_percent <= 0.   
    """
    cgst = sgst = igst = Decimal("0.00")

    if tax_percent > 0:
        if branch_state == party_state:
            tax = (taxable * tax_percent) / 100
            cgst = tax / 2
            sgst = tax / 2
        else:
            igst = (taxable * tax_percent) / 100

    total_tax = cgst + sgst + igst
    return {
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total_tax": total_tax
    }


def to_decimal(value, default=Decimal("0.00")):
    try:
        if value is None or value == "":
            return default
        return Decimal(str(value).replace("%", "").strip())
    except:
        return default


# pos/views/salesentry_views.py
# Find the generate_voucher function and replace with this:

@api_view(["GET"])
def generate_voucher(request):
    branch = request.user.branch
    
    settings_obj = setting.objects.filter(branch=branch).first()
    prefix = getattr(settings_obj, "SI", "SI") if settings_obj else "SI"

    now = datetime.now()
    year = now.year
    if now.month >= 4:
        fy_start = year
        fy_end = year + 1
    else:
        fy_start = year - 1
        fy_end = year

    fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
    pattern = f"{prefix}/{fy}/"

    #  Get last number ONLY for THIS branch
    last_sale = SalesMaster.objects.filter(
        branch=branch,  #  Branch filter
        bill_no__startswith=pattern
    ).order_by("-id").first()

    last_no = 0
    if last_sale and last_sale.bill_no:
        try:
            parts = last_sale.bill_no.split("/")
            if len(parts) >= 3:
                last_no = int(parts[-1])
        except:
            last_no = 0

    next_no = last_no + 1
    voucher_no = f"{pattern}{str(next_no).zfill(4)}"

    

    return Response({
        "voucher_no": voucher_no,
        "last_number": last_no,
        "next_number": next_no,
        "financial_year": fy,
        "prefix": prefix,
        "branch": branch.branch_name,
    })
# Add these methods to SalesEntryCreateAPIView
# pos/views/salesentry_views.py

# pos/views/salesentry_views.py

class SalesEntryCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_branch_from_user(self, user):
        """Get branch associated with the user"""
        try:
            return Branch.objects.get(user=user)
        except Branch.DoesNotExist:
            return None

    #  ReceiveSalesCreditBillCashAPIView ke andar
    def generate_cash_receipt_voucher(self, branch):
        from datetime import datetime
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CR", "CR") if settings_obj else "CR"

        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"  #  pehle define karo

        last_voucher = CashReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern  #  pattern use karo
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        while CashReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        
        return voucher_no

    #  ReceiveSalesCreditBillBankAPIView ke andar
    def generate_bank_receipt_voucher(self, branch):
        from datetime import datetime
        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BR", "BR") if settings_obj else "BR"

        now = datetime.now()
        year = now.year
        fy_start = year if now.month >= 4 else year - 1
        fy_end = fy_start + 1
        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"  #  pehle define karo

        last_voucher = BankReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern  #  pattern use karo
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        while BankReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

       
        return voucher_no

    @transaction.atomic
    def post(self, request):

        
        try:
            # GET BRANCH
            branch = None
            try:
                branch = Branch.objects.get(user=request.user)
            except Branch.DoesNotExist:
                return Response({"error": "No branch found"}, status=400)
            
            
            
            data = request.data
            items_data = data.get("items", [])
            dueDate = data.get("dueDate") or None
            
            settings_obj = setting.objects.filter(branch=branch).first()
            sales_gst_toggle = getattr(settings_obj, 'sales_gst_toggle', True)

            # CREATE SALES MASTER
            sales = SalesMaster.objects.create(
                branch=branch,
                date=data["date"],
                dueDate=dueDate,
                customer_id=data["customer"],
                payment_terms=data["payment_terms"],
                narration=data.get("narration", ""),
                total_basic=Decimal(str(data.get("total_basic", 0))),
                total_discount=Decimal(str(data.get("total_discount", 0))),
                total_tax=Decimal(str(data.get("total_tax", 0))),
                grand_total=Decimal(str(data.get("grand_total", 0))),
                bank_account_id=data.get("bank_account"),
                case_account_id=data.get("cash_account"),
                otherexpnse=Decimal(str(data.get("otherexpnse", 0))),
                frightcharge=Decimal(str(data.get("frightcharge", 0))),
                roundamount=Decimal(str(data.get("roundamount", 0))),
            )
            

            # CREATE ITEMS
            for it in items_data:
                SalesItem.objects.create(
                    sales=sales,
                    item_name_id=it["item_id"],
                    variant_id=it.get("variant_id") or None,
                    hsn_code=it.get("hsn_code", ""),
                    qty=Decimal(str(it.get("qty", 0))),
                    price=Decimal(str(it.get("price", 0))),
                    unit=it.get("unit", ""),
                    discount_percent=Decimal(str(it.get("discount_percent", 0))),
                    tax_percent=Decimal(str(it.get("tax_percent", 0))),
                    basic_amount=Decimal(str(it.get("basic_amount", 0))),
                    discount_amount=Decimal(str(it.get("discount_amount", 0))),
                    tax_amount=Decimal(str(it.get("tax_amount", 0))),
                    net_amount=Decimal(str(it.get("net_amount", 0))),
                    cgst=Decimal(str(it.get("cgst", "0"))),
                    sgst=Decimal(str(it.get("sgst", "0"))),
                    igst=Decimal(str(it.get("igst", "0"))),
                    gst_toggle_status=sales_gst_toggle,
                )
            

            # CREATE RECEIPT
            payment_terms = data["payment_terms"].lower()
            receipt_created = False
            receipt_id = None
            receipt_voucher = None
            
            
            
            if payment_terms == "cash":
                cash_id = data.get("cash_account")
                if cash_id and data.get("customer"):
                    try:
                        voucher = self.generate_cash_receipt_voucher(branch)
                        receipt = CashReceipt.objects.create(
                            date=data["date"],
                            voucher_no=voucher,
                            cash_account_id=cash_id,
                            op_account_id=data["customer"],
                            branch=branch,
                            amount=sales.grand_total,
                            narration=f"Auto receipt - Sale {sales.bill_no}",
                            type="SCR",
                            sales_entry=sales
                        )
                        receipt_created = True
                        receipt_id = receipt.id
                        receipt_voucher = voucher
                       
                    except Exception as e:
                        print(f"❌ SCR FAILED: {e}")
                        
            elif payment_terms == "bank":
                bank_id = data.get("bank_account")
                if bank_id and data.get("customer"):
                    try:
                        voucher = self.generate_bank_receipt_voucher(branch)
                        receipt = BankReceipt.objects.create(
                            date=data["date"],
                            voucher_no=voucher,
                            bank_account_id=bank_id,
                            op_account_id=data["customer"],
                            branch=branch,
                            amount=sales.grand_total,
                            mode="Auto",
                            narration=f"Auto receipt - Sale {sales.bill_no}",
                            type="SBR",
                            sales_entry=sales
                        )
                        receipt_created = True
                        receipt_id = receipt.id
                        receipt_voucher = voucher
                       
                    except Exception as e:
                        print(f" SBR FAILED: {e}")
            else:
                receipt_created = True  # Credit terms

            response_data = {
                "message": "Sales Entry Created",
                "id": sales.id,
                "bill_no": sales.bill_no,
                "branch": branch.branch_name,
                "receipt_created": receipt_created,
            }
            if receipt_id:
                response_data["receipt_id"] = receipt_id
                response_data["receipt_voucher"] = receipt_voucher

            
            return Response(response_data, status=201)

        except Exception as e:
            print(f"❌ FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)
    def generate_bank_receipt_voucher(self, branch):
        from datetime import datetime
        from pos.models.settings import setting

        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BR", "BR") if settings_obj else "BR"

        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year

        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"
        pattern = f"{prefix}/{fy}/"  #  pattern pehle define karo

        last_voucher = BankReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern  #  ab pattern available hai
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        next_no = last_no + 1
        voucher_no = f"{pattern}{str(next_no).zfill(4)}"

        # Uniqueness check
        while BankReceipt.objects.filter(branch=branch, voucher_no=voucher_no).exists():
            next_no += 1
            voucher_no = f"{pattern}{str(next_no).zfill(4)}"

       
        return voucher_no
        
    @transaction.atomic
    def post(self, request):


        try:
            # ── GET BRANCH ──────────────────────────────────────────────
            branch = None
            try:
                branch = Branch.objects.get(user=request.user)
            except Branch.DoesNotExist:
                return Response({"error": "No branch found"}, status=400)

            

            data = request.data
            items_data = data.get("items", [])
            dueDate = data.get("dueDate") or None

            settings_obj = setting.objects.filter(branch=branch).first()
            sales_gst_toggle = getattr(settings_obj, "sales_gst_toggle", True)

            # ── REFERRAL CODE LOOKUP (supports code AND mobile) ────────
            referral_code = (data.get("referral_code") or "").strip() or None
            referral_agent = None

            if referral_code:
                try:
                    from users.models import User as UserModel
                    from mlm.models.agent import Agent
  
                    #  TRY 1: referral_code (UUID) se match
                    try:
                        referral_agent = UserModel.objects.get(referral_code=referral_code)
                        
                    except UserModel.DoesNotExist:
                        pass

                    #  TRY 2: Agent contact_number (mobile) se match
                    if not referral_agent:
                        try:
                            agent = Agent.objects.get(contact_number=referral_code)
                            referral_agent = agent.user
                          
                        except Agent.DoesNotExist:
                            pass

                    #  TRY 3: User phone field se match
                    if not referral_agent:
                        try:
                            referral_agent = UserModel.objects.get(phone=referral_code)
                            
                        except UserModel.DoesNotExist:
                            pass

                    if not referral_agent:
                        
                        referral_code = None

                except Exception as e:
                    
                    referral_code = None

            # ── CREATE SALES MASTER ─────────────────────────────────────
            sales = SalesMaster.objects.create(
                branch=branch,
                date=data["date"],
                dueDate=dueDate,
                customer_id=data["customer"],
                payment_terms=data["payment_terms"],
                narration=data.get("narration", ""),
                total_basic=Decimal(str(data.get("total_basic", 0))),
                total_discount=Decimal(str(data.get("total_discount", 0))),
                total_tax=Decimal(str(data.get("total_tax", 0))),
                grand_total=Decimal(str(data.get("grand_total", 0))),
                bank_account_id=data.get("bank_account"),
                case_account_id=data.get("cash_account"),
                otherexpnse=Decimal(str(data.get("otherexpnse", 0))),
                frightcharge=Decimal(str(data.get("frightcharge", 0))),
                roundamount=Decimal(str(data.get("roundamount", 0))),
                referral_code=referral_code,
                referral_agent=referral_agent,
            )
           

            # ── CREATE ITEMS ────────────────────────────────────────────
            for it in items_data:
                SalesItem.objects.create(
                    sales=sales,
                    item_name_id=it["item_id"],
                    variant_id=it.get("variant_id") or None,
                    hsn_code=it.get("hsn_code", ""),
                    qty=Decimal(str(it.get("qty", 0))),
                    price=Decimal(str(it.get("price", 0))),
                    unit=it.get("unit", ""),
                    discount_percent=Decimal(str(it.get("discount_percent", 0))),
                    tax_percent=Decimal(str(it.get("tax_percent", 0))),
                    basic_amount=Decimal(str(it.get("basic_amount", 0))),
                    discount_amount=Decimal(str(it.get("discount_amount", 0))),
                    tax_amount=Decimal(str(it.get("tax_amount", 0))),
                    net_amount=Decimal(str(it.get("net_amount", 0))),
                    cgst=Decimal(str(it.get("cgst", "0"))),
                    sgst=Decimal(str(it.get("sgst", "0"))),
                    igst=Decimal(str(it.get("igst", "0"))),
                    gst_toggle_status=sales_gst_toggle,
                )
           
            # ── EMAIL RECEIPT TO CUSTOMER ──────────────────────────────
            try:
                from pos.utils.receipt_email import send_sale_receipt_email
                ok, msg = send_sale_receipt_email(sales)
                if not ok:
                    print(f" Receipt email not sent: {msg}")
                else:
                    print(f" Receipt email sent to {sales.customer.email}")
            except Exception as e:
                print(f" Receipt email error: {e}")

            # ── CREATE RECEIPT ──────────────────────────────────────────
            payment_terms = data["payment_terms"].lower()
            try:
                if payment_terms == "cash":
                    cash_account_id = data.get("cash_account")
                    if cash_account_id and data.get("customer"):
                        try:
                            scr_voucher = self.generate_cash_receipt_voucher(branch)
                            CashReceipt.objects.create(
                                date=data["date"],
                                voucher_no=scr_voucher,
                                cash_account_id=cash_account_id,
                                op_account_id=data["customer"],
                                branch=branch,
                                amount=sales.grand_total,
                                narration=f"Auto receipt - Sale {sales.bill_no}",
                                type="SCR",
                                sales_entry=sales,
                            )
                            
                        except Exception as e:
                            print(f" SCR failed: {e}")

                elif payment_terms == "bank":
                    bank_account_id = data.get("bank_account")
                    if bank_account_id and data.get("customer"):
                        try:
                            sbr_voucher = self.generate_bank_receipt_voucher(branch)
                            BankReceipt.objects.create(
                                date=data["date"],
                                voucher_no=sbr_voucher,
                                bank_account_id=bank_account_id,
                                op_account_id=data["customer"],
                                branch=branch,
                                amount=sales.grand_total,
                                mode="Auto",
                                narration=f"Auto receipt - Sale {sales.bill_no}",
                                type="SBR",
                                sales_entry=sales,
                            )
                            
                        except Exception as e:
                            print(f" SBR failed: {e}")
            except Exception as e:
                print(f" Receipt failed but sale saved: {e}")

            # ── MLM / PROFIT DISTRIBUTION ──────────────────────────────
            try:
                from utils.pos_profit_engine import distribute_pos_profit
                from pos.models.pos_profit_settings import POSProfitSettings

                walk_in_toggle = POSProfitSettings.get_toggle()
                payment_terms_lower = data["payment_terms"].lower()

                if payment_terms_lower == "credit":
                    print("   Credit sale — MLM skip, distributes when bills was fully paid")
                else:
                    distribute_pos_profit(
                        pos_sale=sales,
                        branch_user=branch.user,
                        purchaser_user=referral_agent,
                        walk_in_toggle=walk_in_toggle,
                        referral_code_given=bool(referral_code),
                    )
                    sales.mlm_commission_processed = True
                    sales.save(update_fields=["mlm_commission_processed"])
                    print(" MLM distribution complete")

            except Exception as mlm_err:
               
                import traceback
                traceback.print_exc()

            # ── RESPONSE ─────────────────────────────────────────────────
            return Response({
                "message": "Sales Entry Created",
                "id": sales.id,
                "bill_no": sales.bill_no,
                "branch": branch.branch_name,
                "referral_used": bool(referral_code),
            }, status=201)

        except Exception as e:
    
            import traceback
            traceback.print_exc()
            return Response({"error": str(e)}, status=500)


class CustomerListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Account.objects.filter(
            group="Customer",
            branch=request.user.branch
        )
        return Response(qs.values("id", "account_name", "state", "mobile"))
    
class DefaultCustomerAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Get or create default walk-in customer for this branch
        default_customer, created = Account.objects.get_or_create(
            account_name="Default Customer",
            group="Customer",
            branch=request.user.branch,
            defaults={
                'state': request.user.branch.state or 'Maharashtra',
                'mobile': '9999999999',
                'current_balance': 0,
                'current_drcr': 'Dr'
            }
        )
        return Response({
            'id': default_customer.id,
            'account_name': default_customer.account_name
        })        

# pos/views/salesentry_views.py - FINAL CORRECTED SalesItemTaxAPIView

from decimal import Decimal, ROUND_HALF_UP

class SalesItemTaxAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        item_id          = request.data.get("item_id")
        customer_id      = request.data.get("customer_id")
        price            = to_decimal(request.data.get("price"))
        qty              = to_decimal(request.data.get("qty"), 1)
        discount_percent = to_decimal(request.data.get("discount_percent"), 0)

        settings_obj      = setting.objects.filter(branch=request.user.branch).first()
        sales_gst_toggle  = getattr(settings_obj, 'sales_gst_toggle', True)

        if not item_id or not customer_id:
            return Response({"error": "item_id and customer_id required"}, status=400)

        try:
            item = items.objects.select_related("branch").get(id=item_id)
        except items.DoesNotExist:
            return Response({"error": "Item not found"}, status=404)

        try:
            customer = Account.objects.get(id=customer_id, group="Customer")
        except Account.DoesNotExist:
            return Response({"error": "Customer not found"}, status=404)

        tax_percent    = to_decimal(item.taxSlab)
        branch_state   = item.branch.state or ""
        customer_state = customer.state or ""

        # Total price
        total_price = (price * qty).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Discount
        discount_amount       = (total_price * discount_percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        amount_after_discount = (total_price - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        cgst = sgst = igst = total_tax = Decimal("0.00")
        basic_amount = Decimal("0.00")
        net_amount   = Decimal("0.00")

        if tax_percent > 0:
            if sales_gst_toggle:
                # ON: exclusive — tax on top
                total_tax    = (amount_after_discount * tax_percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = amount_after_discount
                net_amount   = (basic_amount + total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                # OFF: inclusive — tax = amount * rate/100, basic = amount - tax
                total_tax    = (amount_after_discount * tax_percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                basic_amount = (amount_after_discount - total_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                net_amount   = amount_after_discount

            # GST Split
            if branch_state == customer_state:
                half_tax = (total_tax / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                cgst     = half_tax
                sgst     = half_tax
                if cgst + sgst != total_tax:
                    if total_tax - (cgst + sgst) > 0:
                        cgst += (total_tax - (cgst + sgst))
            else:
                igst = total_tax
        else:
            basic_amount = amount_after_discount
            net_amount   = amount_after_discount

        return Response({
            "item_id":              item.id,
            "item_name":            item.itemName,
            "customer_id":          customer.id,
            "branch_state":         branch_state,
            "customer_state":       customer_state,
            "tax_percent":          float(tax_percent),
            "sales_gst_toggle":     sales_gst_toggle,
            "basic_amount":         float(basic_amount),
            "total_price":          float(total_price),
            "discount_percent":     float(discount_percent),
            "discount_amount":      float(discount_amount),
            "amount_after_discount":float(amount_after_discount),
            "cgst":                 float(cgst),
            "sgst":                 float(sgst),
            "igst":                 float(igst),
            "total_tax":            float(total_tax),
            "net_amount":           float(net_amount),
        }, status=200)

class SaleItemSearchAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search = request.GET.get("query", "").strip()
        user_branch = request.user.branch

        variants_qs = itemvariants.objects.filter(
            item__branch=user_branch
        ).select_related("item", "item__unit").distinct()

        result = []
        for variant in variants_qs:
            item = variant.item
            
            # Get unit info
            unit_name = "-"
            unit_symbol = "pc"
            unit_supports_fractional = False
            if item.unit:
                unit_name = item.unit.name
                unit_symbol = item.unit.symbol or item.unit.name
                unit_supports_fractional = getattr(item.unit, 'supports_fractional', False)
            
            # Get current stock
            current_stock = 0
            if hasattr(variant, 'current_stock') and variant.current_stock is not None:
                current_stock = variant.current_stock
            elif hasattr(item, 'current_stock') and item.current_stock is not None:
                current_stock = item.current_stock
            
            # current_stock calculation ko fix karo - sabko float mein convert karo
            if current_stock == 0:
                total_purchased = PurchaseItem.objects.filter(
                    variant=variant
                ).aggregate(total=Sum('quantity'))['total'] or 0
                total_sold = SalesItem.objects.filter(
                    variant=variant
                ).aggregate(total=Sum('qty'))['total'] or 0
                opening_stock = variant.opStock if hasattr(variant, 'opStock') and variant.opStock else 0
                #  FIX: Sabko float mein convert karo
                current_stock = float(opening_stock) + float(total_purchased) - float(total_sold)

            # Get sales price
            sales_price = float(variant.salesPrice or variant.purchasePrice or 0)

            #  FIX: Per unit price calculation
            per_unit_price = sales_price  # Default

            if unit_supports_fractional:
                if current_stock > 0:
                    
                    per_unit_price = sales_price 
                else:
              
                    op_stock = float(variant.opStock) if variant.opStock and variant.opStock > 0 else 0
                    if op_stock > 0:
                        per_unit_price = sales_price 
                    else:
                       
                        per_unit_price = sales_price
            else:
                per_unit_price = sales_price
            

            if search:
                search_lower = search.lower()
                match = (
                    search_lower in item.itemName.lower()
                    or search_lower in (item.hsnCode or "").lower()
                    or search_lower in str(sales_price)
                    or search_lower in (variant.size or "").lower()
                    or search_lower in (variant.color or "").lower()
                    or search_lower in (variant.barcode or "").lower()   #  BARCODE FILTER
                    or search_lower in (variant.srno or "").lower()      #  serial number bhi
                )
 
                if not match:
                    continue
            
            result.append({
                "id": variant.id,
                "itemId": item.id,
                "itemName": item.itemName,
                "hsnCode": item.hsnCode or "",
                "salesPrice": float(sales_price), 
                "per_unit_price": float(per_unit_price), 
                "current_stock": float(current_stock),
                "unit": unit_symbol,
                "unit_name": unit_name,
                "unit_supports_fractional": unit_supports_fractional,
                "taxSlab": item.taxSlab or "0",
                "size": variant.size or "-",
                "color": variant.color or "-",
                "srno": variant.srno or "-",
                "barcode": variant.barcode or "",
            })

        return Response(result)
    
class SalesEntryListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_superadmin = user.role == 'superadmin'

        if is_superadmin:
            from pos.models.branch import Branch
            branch_id_param = request.GET.get('branch_id')
            if branch_id_param:
                try:
                    branch = Branch.objects.get(id=branch_id_param)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=404)
            else:
                try:
                    branch = Branch.objects.get(user=user)
                except Branch.DoesNotExist:
                    return Response({'error': 'Branch not found'}, status=400)
        else:
            branch = getattr(user, 'branch', None)
            if not branch:
                return Response({'error': 'Branch not found'}, status=400)

        queryset = SalesMaster.objects.filter(
            branch=branch
        ).order_by("-date", "-id")

        paginator = StandardResultsSetPagination()
        paginated_sales = paginator.paginate_queryset(queryset, request)
        serializer = SalesMasterSerializer(paginated_sales, many=True)
        return paginator.get_paginated_response(serializer.data)


class SaleReceiptView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, sale_id):
        from django.shortcuts import get_object_or_404

        try:
            sale = get_object_or_404(SalesMaster, id=sale_id, branch=request.user.branch)
            branch = get_display_branch_for_sale(sale.branch)  
            customer = sale.customer

            data = {
                "branch_name": branch.branch_name,
                "address": branch.address or "",
                "bill_no": sale.bill_no,
                "date": sale.date.strftime("%d-%m-%Y"),
                "time": sale.created_at.strftime("%H:%M:%S"),
                "customer_name": getattr(customer, "account_name", ""),
                "mobile": customer.mobile if customer else "",
                "payment_mode": sale.payment_terms.capitalize(),
                
                # ✅ FIXED: Consistent naming
                "total_basic": float(sale.total_basic),        # taxable amount
                "total_discount": float(sale.total_discount),  # discount
                "tax_amount": float(sale.total_tax),           # GST total
                "freight": float(sale.frightcharge or 0),
                "other_expense": float(sale.otherexpnse or 0),
                "round_off": float(sale.roundamount or 0),
                "grand_total": float(sale.grand_total),        # final payable
                
                # Legacy aliasesताकि purane frontend break na ho
                "total_amount": float(sale.total_basic),
                "discount": float(sale.total_discount),
                "net_amount": float(sale.grand_total),

                "items": [
                    {
                        "name": item.item_name.itemName,
                        "qty": float(item.qty),
                        "price": float(item.price),
                        # ✅ FIXED: net_amount = what customer pays per item
                        "amount": float(item.net_amount),
                        "basic": float(item.basic_amount),
                        "tax": float(item.tax_amount),
                        "discount": float(item.discount_amount),
                    }
                    for item in sale.items.all()
                ],
            }
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReceiveSalesCreditBillCashAPIView(APIView):
    """Receive payment for a sales credit bill via cash receipt (creates SCR)"""
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        data = request.data
        sales_bill_id = data.get('sales_bill_id')
        cash_account_id = data.get('cash_account')
        amount = Decimal(str(data.get('amount', 0)))
        
        try:
            sales_bill = SalesMaster.objects.get(
                id=sales_bill_id,
                branch=request.user.branch,
                payment_terms__iexact='credit'
            )
            
            scr_voucher = self.generate_cash_receipt_voucher(request.user.branch)
            
            cash_receipt = CashReceipt.objects.create(
                date=data['date'],
                voucher_no=scr_voucher,
                cash_account_id=cash_account_id,
                op_account_id=sales_bill.customer.id,
                branch=request.user.branch,
                amount=amount,
                narration=f"Payment received against sales credit bill {sales_bill.bill_no}",
                type="SCR",   #  correct
                sales_entry=sales_bill
            )

            # 🔥 FORCE UPDATE (important)
            if cash_receipt.type != "SCR":
                cash_receipt.type = "SCR"
                cash_receipt.save(update_fields=["type"])
            
            from django.db.models import Sum as DjangoSum
            from pos.models.cashreceipt import CashReceipt as CR
            from pos.models.bankreceipt import BankReceipt as BR

            total_received = CR.objects.filter(
                sales_entry=sales_bill
            ).aggregate(total=DjangoSum('amount'))['total'] or Decimal('0')

            total_received += BR.objects.filter(
                sales_entry=sales_bill
            ).aggregate(total=DjangoSum('amount'))['total'] or Decimal('0')

            pending = sales_bill.grand_total - total_received
           

            if pending <= Decimal('0.005') and not sales_bill.mlm_commission_processed:
                try:
                    from utils.pos_profit_engine import distribute_pos_profit
                    from pos.models.pos_profit_settings import POSProfitSettings

                    walk_in_toggle = POSProfitSettings.get_toggle()
                    distribute_pos_profit(
                        pos_sale=sales_bill,
                        branch_user=sales_bill.branch.user,
                        purchaser_user=sales_bill.referral_agent,
                        walk_in_toggle=walk_in_toggle,
                        referral_code_given=bool(sales_bill.referral_code),
                    )
                    sales_bill.mlm_commission_processed = True
                    sales_bill.save(update_fields=["mlm_commission_processed"])
                   
                except Exception as mlm_err:
                   pass

            return Response({
                'success': True,
                'message': 'Sales credit bill payment received successfully',
                'receipt': {
                    'id': cash_receipt.id,
                    'voucher_no': cash_receipt.voucher_no,
                    'amount': float(cash_receipt.amount),
                    'type': cash_receipt.type
                }
            }, status=status.HTTP_201_CREATED)
            
        except SalesMaster.DoesNotExist:
            return Response({'error': 'Sales bill not found'}, status=404)
    
    def generate_cash_receipt_voucher(self, branch):
        """Generate voucher number for SCR"""
        from datetime import datetime
        from pos.models.settings import setting

        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "CR", "CR") if settings_obj else "CR"

        #  STEP 1: FY pehle banao
        now = datetime.now()
        year = now.year

        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year

        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"

        #  STEP 2: ab pattern banao
        pattern = f"{prefix}/{fy}/"

        #  STEP 3: last voucher nikalo
        last_voucher = CashReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        #  STEP 4: next voucher
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{pattern}{next_no}"

        return voucher_no




class SalesCreditBillsAPIView(APIView):
    """Get sales credit bills with pending amount.
    
    🔥 LOGIC (Same as PurchaseCreditBillsAPIView):
    - SCR/SBR receipts reduce pending
    - Credit Returns jinka SRCP/SRBP payment already kiya → DON'T reduce pending
    - Credit Returns jinka koi payment nahi kiya → REDUCE pending (auto-adjusted)
    """
    permission_classes = [IsAuthenticated]
 
    def get(self, request):
        from django.db.models import Q, Sum
        from decimal import Decimal
        from pos.models.salesreturn import SalesReturnMaster
 
        search = request.GET.get('query', '').strip()
 
        bills = SalesMaster.objects.filter(
            branch=request.user.branch,
            payment_terms__iexact='credit'
        )
 
        if search:
            bills = bills.filter(
                Q(bill_no__icontains=search) |
                Q(customer__account_name__icontains=search)
            )
 
        bills_data = []
        for bill in bills:
            # Receipts already collected (SCR/SBR)
            total_paid = CashReceipt.objects.filter(
                sales_entry=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
 
            total_paid += BankReceipt.objects.filter(
                sales_entry=bill
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
 
            # ALL returns for display
            all_returns = SalesReturnMaster.objects.filter(
                branch=request.user.branch,
                original_bill_no=bill.bill_no,
            )
            total_all_returned = all_returns.aggregate(
                total=Sum('grand_total')
            )['total'] or Decimal('0')
            
            # 🔥 Credit Returns jo ABHI TAK settled nahi hue
            # Settled = jinka SRCP/SRBP payment kiya ja chuka hai
            credit_returns_unsettled = Decimal('0')
            
            for sr in all_returns.filter(payment_terms__iexact='credit'):
                # Check SRCP/SRBP payments against this return
                sr_payments = CashPayment.objects.filter(
                    sales_return=sr
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                
                sr_payments += BankPayment.objects.filter(
                    sales_return=sr
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                
                if sr_payments >= sr.grand_total:
                    # Fully paid → Settled, DON'T reduce pending
                    print(f"  SR {sr.return_no}: Fully paid ₹{sr_payments} → Won't reduce pending")
                else:
                    # Not paid or partially paid → Pending return
                    unsettled = sr.grand_total - sr_payments
                    credit_returns_unsettled += unsettled
                    
            
            # 🔥 Pending = Grand - Receipts - Unsettled Credit Returns
            pending_amount = bill.grand_total - total_paid - credit_returns_unsettled
            
           
 
            if pending_amount > Decimal('0.005'):
                bills_data.append({
                    'id': bill.id,
                    'billNo': bill.bill_no,
                    'partyName__account_name': bill.customer.account_name,
                    'party_id': bill.customer.id,
                    'date': bill.date.strftime('%Y-%m-%d'),
                    'grand_total': float(bill.grand_total),
                    'paid_amount': float(total_paid),
                    'returned_amount': float(total_all_returned),
                    'pending_amount': float(pending_amount),
                })
 
        return Response({'type': 'sales', 'bills': bills_data})


class ReceiveSalesCreditBillBankAPIView(APIView):
    """Receive payment for a sales credit bill via bank receipt (creates SBR)"""
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        data = request.data
        sales_bill_id = data.get('sales_bill_id')
        bank_account_id = data.get('bank_account')
        amount = Decimal(str(data.get('amount', 0)))
        mode = data.get('mode', 'UPI')
        
        try:
            sales_bill = SalesMaster.objects.get(
                id=sales_bill_id,
                branch=request.user.branch,
                payment_terms__iexact='credit'
            )
            
            sbr_voucher = self.generate_bank_receipt_voucher(request.user.branch)
            
            bank_receipt = BankReceipt.objects.create(
                date=data['date'],
                voucher_no=sbr_voucher,
                bank_account_id=bank_account_id,
                op_account_id=sales_bill.customer.id,
                branch=request.user.branch,
                amount=amount,
                mode=mode,
                cheque_no=data.get('cheque_no'),
                cheque_date=data.get('cheque_date'),
                cheque_clear_date=data.get('cheque_clear_date'),
                narration=f"Payment received against sales credit bill {sales_bill.bill_no}",
                type="SBR",
                sales_entry=sales_bill
            )
            
            from django.db.models import Sum as DjangoSum
            from pos.models.cashreceipt import CashReceipt as CR
            from pos.models.bankreceipt import BankReceipt as BR

            total_received = CR.objects.filter(
                sales_entry=sales_bill
            ).aggregate(total=DjangoSum('amount'))['total'] or Decimal('0')

            total_received += BR.objects.filter(
                sales_entry=sales_bill
            ).aggregate(total=DjangoSum('amount'))['total'] or Decimal('0')

            pending = sales_bill.grand_total - total_received
           

            if pending <= Decimal('0.005') and not sales_bill.mlm_commission_processed:
                try:
                    from utils.pos_profit_engine import distribute_pos_profit
                    from pos.models.pos_profit_settings import POSProfitSettings

                    walk_in_toggle = POSProfitSettings.get_toggle()
                    distribute_pos_profit(
                        pos_sale=sales_bill,
                        branch_user=sales_bill.branch.user,
                        purchaser_user=sales_bill.referral_agent,
                        walk_in_toggle=walk_in_toggle,
                        referral_code_given=bool(sales_bill.referral_code),
                    )
                    sales_bill.mlm_commission_processed = True
                    sales_bill.save(update_fields=["mlm_commission_processed"])
                 
                except Exception as mlm_err:
                   pass

            
            return Response({
                'success': True,
                'message': 'Sales credit bill payment received successfully',
                'receipt': {
                    'id': bank_receipt.id,
                    'voucher_no': bank_receipt.voucher_no,
                    'amount': float(bank_receipt.amount),
                    'type': bank_receipt.type
                }
            }, status=status.HTTP_201_CREATED)
            
        except SalesMaster.DoesNotExist:
            return Response({'error': 'Sales bill not found'}, status=404)
    
    def generate_bank_receipt_voucher(self, branch):
        """Generate voucher number for SBR"""
        from datetime import datetime
        from pos.models.settings import setting

        settings_obj = setting.objects.filter(branch=branch).first()
        prefix = getattr(settings_obj, "BR", "BR") if settings_obj else "BR"

        #  STEP 1: Financial Year
        now = datetime.now()
        year = now.year
        if now.month >= 4:
            fy_start = year
            fy_end = year + 1
        else:
            fy_start = year - 1
            fy_end = year

        fy = f"{str(fy_start)[2:]}-{str(fy_end)[2:]}"

        #  STEP 2: pattern (IMPORTANT)
        pattern = f"{prefix}/{fy}/"

        #  STEP 3: filter by pattern
        last_voucher = BankReceipt.objects.filter(
            branch=branch,
            voucher_no__startswith=pattern
        ).order_by("-id").first()

        last_no = 0
        if last_voucher and last_voucher.voucher_no:
            try:
                last_no = int(last_voucher.voucher_no.split("/")[-1])
            except (ValueError, IndexError):
                last_no = 0

        #  STEP 4: next number
        next_no = str(last_no + 1).zfill(4)
        voucher_no = f"{pattern}{next_no}"

        return voucher_no