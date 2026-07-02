# pos/models/group_unit.py
from django.db import models
from pos.models.branch import Branch


class ItemGroup(models.Model):
    """Group model that belongs to a specific branch"""
    name = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='item_groups')
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['name', 'branch']
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.branch.branch_name})"


UNIT_TYPE_CHOICES = [
    ('weight', 'Weight'),       # kg, g, mg, lb, oz
    ('volume', 'Volume'),       # ltr, ml, gallon
    ('length', 'Length'),       # meter, cm, inch, feet
    ('count', 'Count'),         # piece, dozen, box, pack
    ('area', 'Area'),           # sq_ft, sq_meter
    ('other', 'Other'),
]


class ItemUnit(models.Model):
    """
    GLOBAL unit table - sabhi branches ke liye same units.
    Branch-specific nahi hai ab.
    Agar unit_type = 'weight' aur symbol = 'kg' hai toh
    proportional calculation lagegi.
    """
    name = models.CharField(max_length=50, unique=True)      # e.g. Kilogram, Liter
    symbol = models.CharField(max_length=10, unique=True)     # e.g. kg, ltr, pc
    unit_type = models.CharField(
        max_length=20,
        choices=UNIT_TYPE_CHOICES,
        default='count'
    )
    # Kya yeh unit weight-based proportional calculation support karta hai?
    # KG, G, LB etc ke liye True hoga
    supports_fractional = models.BooleanField(
        default=False,
        help_text="True for weight/volume units like kg, ltr where 10kg @300 => 1kg @30"
    )
    # Base unit conversion factor (future use ke liye)
    # e.g. 1 kg = 1000 g, toh g ka conversion_factor = 0.001 hoga
    conversion_to_base = models.FloatField(
        default=1.0,
        help_text="Conversion factor to base unit (e.g., g -> kg = 0.001)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.symbol})"

    def calculate_price_for_quantity(self, base_price: float, base_quantity: float, sold_quantity: float) -> float:
        """
        Proportional price calculate karo.
        Example: 30 kg ka price 300 rupees hai.
        10 kg becha => 300 / 30 * 10 = 100 rupees
        
        Args:
            base_price: Total price for base_quantity (e.g., 300 for 30kg)
            base_quantity: Base quantity (e.g., 30 kg)
            sold_quantity: Quantity sold (e.g., 10 kg)
        
        Returns:
            Calculated price for sold_quantity
        """
        if not self.supports_fractional or base_quantity <= 0:
            return base_price
        
        unit_price = base_price * base_quantity
        return round(unit_price * sold_quantity, 2)