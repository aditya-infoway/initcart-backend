# pos/views/account_views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, permissions
from django.db.models import Q

from pos.models.account import Account
from pos.models.branch import Branch
from pos.serializers.account_serializer import AccountSerializer, SupplierSerializer, AccountviewSerializer, AccountTermsSerializers
from pos.utils.pagination import StandardResultsSetPagination  


class AccountCreateView(APIView):
    permission_classes = [IsAuthenticated]

    """ API View for creating a new account. """
    def post(self, request):
        # Automatically assign the branch from logged-in user
        data = request.data.copy()
        data['branch'] = request.user.branch.id  # assign branch_id

        serializer = AccountSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Account created successfully", "account": serializer.data},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class SupplierListAPIView(APIView): 
    permission_classes = [IsAuthenticated] 
    def get(self, request): 
        suppliers = Account.objects.filter(group="Supplier", branch=request.user.branch) 
        serializer = SupplierSerializer(suppliers, many=True) 
        return Response(serializer.data)
    

class AccountAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get all accounts for the user's branch except Cash and Bank accounts
        accounts = Account.objects.filter(
            branch=request.user.branch
        ).exclude(
            Q(group__iexact="Case In Hand") | Q(group__iexact="Bank Account")
        ).order_by('-id')  # ✅ ORDER BY add kiya

        # ✅ PAGINATION ADD KARO
        paginator = StandardResultsSetPagination()
        paginated_accounts = paginator.paginate_queryset(accounts, request)
        
        serializer = SupplierSerializer(paginated_accounts, many=True)
        
        # ✅ Paginated response return karo
        return paginator.get_paginated_response(serializer.data)


class AccountListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_branch = getattr(request.user, "branch", None)
        if not user_branch:
            return Response(
                {"error": "User branch not found"},
                status=status.HTTP_400_BAD_REQUEST
            )

        accounts = Account.objects.filter(branch=user_branch).order_by('-id')  # ✅ ORDER BY add kiya
        
        # ✅ PAGINATION ADD KARO
        paginator = StandardResultsSetPagination()
        paginated_accounts = paginator.paginate_queryset(accounts, request)
        
        serializer = AccountviewSerializer(paginated_accounts, many=True)
        
        # ✅ Paginated response return karo
        return paginator.get_paginated_response(serializer.data)
    

class AccountUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"  # URL will use /api/account/<id>/
    

class AccountsByTermsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        terms = request.query_params.get('terms', None)

        if not terms:
            return Response({"error": "terms parameter is required"}, status=400)

        terms = terms.lower()
        branch = request.user.branch  # current user's branch

        if terms == "credit":
            accounts = Account.objects.none()
        elif terms == "cash":
            accounts = Account.objects.filter(
                branch_id=branch,
                group__icontains="Case In Hand"
            ).order_by('-id')
        elif terms == "bank":
            accounts = Account.objects.filter(
                branch_id=branch,
                group__icontains="Bank Account"
            ).order_by('-id')
        else:
            accounts = Account.objects.none()

        serializer = AccountTermsSerializers(accounts, many=True)
        return Response(serializer.data)
    
    
class AccountTypeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        account_type = request.query_params.get("type", "").strip()
        user = request.user

        try:
            user_branch = Branch.objects.get(user=user)
        except Branch.DoesNotExist:
            return Response({"error": "User branch not found"}, status=400)

        accounts = Account.objects.filter(branch=user_branch.id).order_by('-id')

        if account_type:
            accounts = accounts.filter(group__iexact=account_type)
        else:
            accounts = accounts.filter(group__in=["Bank Account", "Case In Hand"])

        serializer = AccountTermsSerializers(accounts, many=True)
        return Response(serializer.data)
    

class CustomerCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data.copy()
        data['branch'] = request.user.branch.id
        data['group'] = 'Customer'
        data['drcr'] = 'Dr'
        data['current_balance'] = 0
        
        serializer = AccountSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Customer created successfully",
                "customer": serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
from ecommerce.permissions import IsSuperAdmin
from pos.models.branch import Branch


class BranchLinkableAccountsAPIView(APIView):
    """
    GET /api/branch-linkable-accounts/?branch_id=<id optional>
    Sirf superadmin. Already kisi branch se linked accounts exclude ho jayenge,
    except agar ?branch_id diya hai (edit mode) — tab uss branch ke apne current
    selections wapas dikhenge taaki dropdown me apna hi selection dikhta rahe.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        branch_id = request.query_params.get('branch_id', '').strip()

        linked_debitor_ids = set(
            Branch.objects.exclude(sundry_debitor_account__isnull=True)
            .values_list('sundry_debitor_account_id', flat=True)
        )
        linked_creditor_ids = set(
            Branch.objects.exclude(sundry_creditor_account__isnull=True)
            .values_list('sundry_creditor_account_id', flat=True)
        )
        all_linked_ids = linked_debitor_ids | linked_creditor_ids

        if branch_id:
            try:
                current = Branch.objects.get(id=branch_id)
                all_linked_ids.discard(current.sundry_debitor_account_id)
                all_linked_ids.discard(current.sundry_creditor_account_id)
            except Branch.DoesNotExist:
                pass

        debitor_qs = Account.objects.filter(
            group__in=['Customer - Sundry Debitor', 'Sundry Debitor(Internal)']
        ).exclude(id__in=all_linked_ids).order_by('account_name')

        creditor_qs = Account.objects.filter(
            group__in=['Supplier - Sundry Creditor', 'Sundry Creditor(Internal)']
        ).exclude(id__in=all_linked_ids).order_by('account_name')

        return Response({
            "debitor_accounts": [
                {"id": a.id, "account_name": a.account_name, "group": a.group} for a in debitor_qs
            ],
            "creditor_accounts": [
                {"id": a.id, "account_name": a.account_name, "group": a.group} for a in creditor_qs
            ],
        })
        
        
            
    