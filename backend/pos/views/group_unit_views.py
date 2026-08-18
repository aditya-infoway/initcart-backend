from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db import models

from pos.models.group_unit import ItemGroup, ItemUnit
from pos.serializers.group_unit_serializers import (
    ItemGroupSerializer, ItemUnitSerializer,
    GroupCreateSerializer, UnitCreateSerializer
)
from pos.utils.pagination import StandardResultsSetPagination

# ✅ ADD: Permission imports
from ecommerce.permissions import IsSuperAdminOrBranchOrPagePermittedEmployee



# ─────────────────────────────────────────────────────────────────────────────
# MAIN GROUP CRUD (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class GroupListCreateAPI(APIView):
    """List all groups for current branch or create a new group"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/createGroup"  # ✅ ADD: Frontend route
    
    def get(self, request):
        """Get all groups for the user's branch WITH PAGINATION"""
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        groups = ItemGroup.objects.filter(branch=branch).order_by('-created_at')
        
        paginator = StandardResultsSetPagination()
        paginated_groups = paginator.paginate_queryset(groups, request)
        
        serializer = ItemGroupSerializer(paginated_groups, many=True)
        
        return paginator.get_paginated_response({
            'success': True,
            'groups': serializer.data
        })
    
    def post(self, request):
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # ✅ ADD context with request
        serializer = GroupCreateSerializer(
            data=request.data,
            context={'request': request}   # ✅ ADD
        )
        
        if serializer.is_valid():
            # ✅ Use serializer.save() instead of manual create
            group = serializer.save(branch=branch)   # ✅ CHANGE
            return Response({
                'success': True,
                'message': 'Group created successfully',
                'group': ItemGroupSerializer(group).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
class GroupDetailAPI(APIView):
    """Update or delete a specific group"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/createGroup"  # ✅ ADD: Frontend route
    
    def get_object(self, pk, branch):
        try:
            return ItemGroup.objects.get(id=pk, branch=branch)
        except ItemGroup.DoesNotExist:
            return None
    
    def put(self, request, pk):
        """Update group"""
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        group = self.get_object(pk, branch)
        
        if not group:
            return Response({
                'success': False,
                'message': 'Group not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        group.name = request.data.get('name', group.name)
        group.description = request.data.get('description', group.description)
        group.save()
        
        return Response({
            'success': True,
            'message': 'Group updated successfully',
            'group': ItemGroupSerializer(group).data
        })
    
    def delete(self, request, pk):
        """Delete group (only if no items use it)"""
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        group = self.get_object(pk, branch)
        
        if not group:
            return Response({
                'success': False,
                'message': 'Group not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if group is used by any items
        if group.items.exists():
            return Response({
                'success': False,
                'message': f'Cannot delete group "{group.name}" as it is used by {group.items.count()} item(s)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        group.delete()
        return Response({
            'success': True,
            'message': 'Group deleted successfully'
        })


# ─────────────────────────────────────────────────────────────────────────────
# MAIN UNIT CRUD (with permission check)
# ─────────────────────────────────────────────────────────────────────────────

class UnitListCreateAPI(APIView):
    """List all global units or create new (admin only)"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/createGroup"  # ✅ ADD: Frontend route

    def get(self, request):
        """Get all units WITH PAGINATION"""
        
        # ✅ ADD: Effective branch check (though units are global, still need user validation)
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        units = ItemUnit.objects.filter(is_active=True).order_by('unit_type', 'name')
        
        paginator = StandardResultsSetPagination()
        paginated_units = paginator.paginate_queryset(units, request)
        serializer = ItemUnitSerializer(paginated_units, many=True)
        
        return paginator.get_paginated_response({
            'success': True,
            'units': serializer.data
        })

    def post(self, request):
        """Create a new global unit"""
        
        # ✅ ADD: Effective branch check
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = UnitCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            unit = serializer.save()
            return Response({
                'success': True,
                'message': 'Unit created successfully',
                'unit': ItemUnitSerializer(unit).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UnitDetailAPI(APIView):
    """Update or delete a specific unit"""
    
    # ✅ CHANGE: IsAuthenticated → IsSuperAdminOrBranchOrPagePermittedEmployee
    permission_classes = [IsSuperAdminOrBranchOrPagePermittedEmployee]
    page_key = "/createGroup"  # ✅ ADD: Frontend route
    
    def get_object(self, pk, branch):
        try:
            return ItemUnit.objects.get(id=pk, branch=branch)
        except ItemUnit.DoesNotExist:
            return None
    
    def put(self, request, pk):
        """Update unit"""
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        unit = self.get_object(pk, branch)
        
        if not unit:
            return Response({
                'success': False,
                'message': 'Unit not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        unit.name = request.data.get('name', unit.name)
        unit.symbol = request.data.get('symbol', unit.symbol)
        unit.description = request.data.get('description', unit.description)
        unit.save()
        
        return Response({
            'success': True,
            'message': 'Unit updated successfully',
            'unit': ItemUnitSerializer(unit).data
        })
    
    def delete(self, request, pk):
        """Delete unit (only if no items use it)"""
        
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        unit = self.get_object(pk, branch)
        
        if not unit:
            return Response({
                'success': False,
                'message': 'Unit not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if unit is used by any items
        if unit.items.exists():
            return Response({
                'success': False,
                'message': f'Cannot delete unit "{unit.name}" as it is used by {unit.items.count()} item(s)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        unit.delete()
        return Response({
            'success': True,
            'message': 'Unit deleted successfully'
        })


# ─────────────────────────────────────────────────────────────────────────────
# DROPDOWN HELPER APIS — NO PERMISSION GATE (only IsAuthenticated)
# ─────────────────────────────────────────────────────────────────────────────

class AllGroupsListAPI(APIView):
    """Get all groups without pagination (for dropdowns)"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # ✅ CHANGE: request.user.branch → get_effective_branch()
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        groups = ItemGroup.objects.filter(branch=branch).order_by('name')
        serializer = ItemGroupSerializer(groups, many=True)
        return Response({
            'success': True,
            'groups': serializer.data
        })


class AllUnitsListAPI(APIView):
    """Get all GLOBAL units for dropdown - no branch filter"""
    
    # ✅ KEEP: IsAuthenticated (helper API, no page_key needed)
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ✅ ADD: Basic branch validation (even though units are global)
        branch = request.user.get_effective_branch()
        if not branch:
            return Response({
                'success': False,
                'message': 'No branch linked to this user'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Ab branch filter nahi - global units
        units = ItemUnit.objects.filter(is_active=True).order_by('unit_type', 'name')
        serializer = ItemUnitSerializer(units, many=True)
        return Response({
            'success': True,
            'units': serializer.data
        })