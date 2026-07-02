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
from pos.utils.pagination import StandardResultsSetPagination  # ✅ IMPORTANT: Yeh line add karo


class GroupListCreateAPI(APIView):
    """List all groups for current branch or create a new group"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all groups for the user's branch WITH PAGINATION"""
        branch = request.user.branch
        # ✅ ORDER BY add kiya for consistent ordering
        groups = ItemGroup.objects.filter(branch=branch).order_by('-created_at')
        
        # ✅ YAHI SE PAGINATION START HOTI HAI
        paginator = StandardResultsSetPagination()
        paginated_groups = paginator.paginate_queryset(groups, request)
        # ✅ YAHI TAK PAGINATION
        
        serializer = ItemGroupSerializer(paginated_groups, many=True)
        
        # ✅ Paginated response return karo
        return paginator.get_paginated_response({
            'success': True,
            'groups': serializer.data
        })
    
    def post(self, request):
        """Create a new group for the branch"""
        branch = request.user.branch
        serializer = GroupCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            group = ItemGroup.objects.create(
                name=serializer.validated_data['name'],
                description=serializer.validated_data.get('description', ''),
                branch=branch
            )
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
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk, branch):
        try:
            return ItemGroup.objects.get(id=pk, branch=branch)
        except ItemGroup.DoesNotExist:
            return None
    
    def put(self, request, pk):
        """Update group"""
        branch = request.user.branch
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
        branch = request.user.branch
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


# pos/views/group_unit_views.py mein AllUnitsListAPI update karo

class UnitListCreateAPI(APIView):
    """List all global units or create new (admin only)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        units = ItemUnit.objects.filter(is_active=True).order_by('unit_type', 'name')
        
        paginator = StandardResultsSetPagination()
        paginated_units = paginator.paginate_queryset(units, request)
        serializer = ItemUnitSerializer(paginated_units, many=True)
        
        return paginator.get_paginated_response({
            'success': True,
            'units': serializer.data
        })

    def post(self, request):
        """Naya global unit banao - ideally admin only"""
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
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk, branch):
        try:
            return ItemUnit.objects.get(id=pk, branch=branch)
        except ItemUnit.DoesNotExist:
            return None
    
    def put(self, request, pk):
        """Update unit"""
        branch = request.user.branch
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
        branch = request.user.branch
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
        
#this both below api is only for dropdowns 
class AllGroupsListAPI(APIView):
    """Get all groups without pagination (for dropdowns)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        branch = request.user.branch
        groups = ItemGroup.objects.filter(branch=branch).order_by('name')
        serializer = ItemGroupSerializer(groups, many=True)
        return Response({
            'success': True,
            'groups': serializer.data
        })


class AllUnitsListAPI(APIView):
    """Get all GLOBAL units for dropdown - no branch filter"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Ab branch filter nahi - global units
        units = ItemUnit.objects.filter(is_active=True).order_by('unit_type', 'name')
        serializer = ItemUnitSerializer(units, many=True)
        return Response({
            'success': True,
            'units': serializer.data
        })       