# pos/views/franchise_branch_views.py
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from django_filters.rest_framework import DjangoFilterBackend

from pos.models.branch import Branch
from pos.serializers.franchise_branch_serializers import (
    FranchiseBranchCreateSerializer,
    FranchiseBranchListSerializer,
    FranchiseBranchUpdateSerializer,
)
from ecommerce.permissions import IsFranchiseOrPagePermittedEmployee


class MyBranchesViewSet(viewsets.ModelViewSet):
    """
    'My Branches' — Franchise (ownership_type='franchise') aur uske
    permitted employees ke liye. Sirf apne banaye hue Branches
    (parent_franchise = apni khud ki branch) dikhte/edit hote hain.
    """
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsFranchiseOrPagePermittedEmployee]
    page_key = "/myBranches"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["branch_name", "owner_name", "email", "phone", "city", "state"]
    filterset_fields = ["status"]

    def get_franchise_branch(self, request):
        return request.user.get_effective_branch()

    def get_queryset(self):
        franchise_branch = self.get_franchise_branch(self.request)
        if not franchise_branch:
            return Branch.objects.none()
        return Branch.objects.filter(parent_franchise=franchise_branch).order_by("-created_at")

    def get_serializer_class(self):
        if self.action == "create":
            return FranchiseBranchCreateSerializer
        if self.action in ["update", "partial_update"]:
            return FranchiseBranchUpdateSerializer
        return FranchiseBranchListSerializer

    def create(self, request, *args, **kwargs):
        franchise_branch = self.get_franchise_branch(request)
        if not franchise_branch:
            return Response({"success": False, "message": "Franchise profile not found."}, status=400)

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request, "parent_franchise": franchise_branch},
        )
        if serializer.is_valid():
            branch = serializer.save()
            return Response({
                "success": True,
                "message": "Branch created successfully!",
                "data": FranchiseBranchListSerializer(branch).data
            }, status=201)
        return Response({"success": False, "errors": serializer.errors}, status=400)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                "success": True, "data": serializer.data, "count": queryset.count()
            })
        serializer = self.get_serializer(queryset, many=True)
        return Response({"success": True, "data": serializer.data, "count": queryset.count()})

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({"success": True, "data": serializer.data})

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "message": "Branch updated successfully!",
                "data": serializer.data
            })
        return Response({"success": False, "errors": serializer.errors}, status=400)

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"success": True, "message": "Branch deleted successfully"}, status=200)
        except Exception as e:
            return Response({"success": False, "message": str(e)}, status=400)

    @action(detail=True, methods=["post"])
    def change_status(self, request, pk=None):
        branch = self.get_object()
        new_status = request.data.get("status")
        if new_status not in ["active", "inactive"]:
            return Response(
                {"success": False, "message": 'Invalid status. Use "active" or "inactive"'}, status=400
            )
        branch.status = new_status
        branch.save(update_fields=["status"])
        return Response({
            "success": True,
            "message": f"Branch status changed to {new_status}",
            "data": FranchiseBranchListSerializer(branch).data
        })

    @action(detail=False, methods=["get"])
    def my_tax_details(self, request):
        """Franchise ka apna GST/PAN — create-modal me read-only dikhane ke liye."""
        franchise_branch = self.get_franchise_branch(request)
        if not franchise_branch:
            return Response({"success": False, "message": "Franchise profile not found."}, status=404)
        return Response({
            "success": True,
            "data": {
                "gst_number": franchise_branch.gst_number or "",
                "pan_number": franchise_branch.pan_number or "",
            }
        })