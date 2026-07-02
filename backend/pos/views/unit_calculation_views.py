# pos/views/unit_calculation_views.py - NEW FILE

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from pos.models.group_unit import ItemUnit


class UnitPriceCalculationAPI(APIView):
    """
    KG-based ya kisi bhi fractional unit ke liye price calculate karo.
    
    Use case:
    - Item hai 30 KG @ 300 rupees purchase price
    - Sale karna hai 10 KG
    - Ye API batayegi 10 KG ka price = 100 rupees
    
    POST body:
    {
        "unit_id": 1,           # ItemUnit ka ID
        "base_quantity": 30,    # Kitne mein purchase hua (e.g., 30 kg)
        "base_price": 300,      # Uska price (e.g., 300 rupees)
        "sold_quantity": 10     # Kitna becha ja raha hai (e.g., 10 kg)
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        unit_id = request.data.get('unit_id')
        base_quantity = request.data.get('base_quantity')
        base_price = request.data.get('base_price')
        sold_quantity = request.data.get('sold_quantity')

        # Validation
        if not all([unit_id, base_quantity, base_price, sold_quantity]):
            return Response({
                'success': False,
                'message': 'unit_id, base_quantity, base_price, sold_quantity sab required hain'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            unit = ItemUnit.objects.get(id=unit_id)
        except ItemUnit.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Unit not found'
            }, status=status.HTTP_404_NOT_FOUND)

        base_quantity = float(base_quantity)
        base_price = float(base_price)
        sold_quantity = float(sold_quantity)

        if base_quantity <= 0:
            return Response({
                'success': False,
                'message': 'base_quantity 0 se zyada hona chahiye'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate
        calculated_price = unit.calculate_price_for_quantity(
            base_price=base_price,
            base_quantity=base_quantity,
            sold_quantity=sold_quantity
        )

        unit_price = round(base_price / base_quantity, 4) if unit.supports_fractional else base_price

        return Response({
            'success': True,
            'unit': {
                'id': unit.id,
                'name': unit.name,
                'symbol': unit.symbol,
                'supports_fractional': unit.supports_fractional
            },
            'calculation': {
                'base_quantity': base_quantity,
                'base_price': base_price,
                'sold_quantity': sold_quantity,
                'unit_price': unit_price,          # Per unit price (e.g., 10 rs/kg)
                'calculated_price': calculated_price,  # Total for sold qty (e.g., 100 rs for 10kg)
                'currency': 'INR'
            },
            'formula': f"{base_price} / {base_quantity} × {sold_quantity} = {calculated_price}" if unit.supports_fractional else "Fixed price unit - no proportional calculation"
        })


class GetUnitsByTypeAPI(APIView):
    """Unit type ke hisaab se filter karo dropdown ke liye"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        unit_type = request.GET.get('type', None)
        
        qs = ItemUnit.objects.filter(is_active=True)
        if unit_type:
            qs = qs.filter(unit_type=unit_type)
        
        qs = qs.order_by('unit_type', 'name')
        
        units = [{
            'id': u.id,
            'name': u.name,
            'symbol': u.symbol,
            'unit_type': u.unit_type,
            'supports_fractional': u.supports_fractional
        } for u in qs]

        return Response({
            'success': True,
            'units': units,
            'unit_types': [
                {'value': 'weight', 'label': 'Weight (kg, g, lb...)'},
                {'value': 'volume', 'label': 'Volume (ltr, ml...)'},
                {'value': 'length', 'label': 'Length (m, cm, ft...)'},
                {'value': 'count', 'label': 'Count (pc, box, dozen...)'},
                {'value': 'area', 'label': 'Area (sqft, sqm...)'},
            ]
        })