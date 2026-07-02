from django.db import migrations

PREDEFINED_UNITS = [
    {'name': 'Kilogram', 'symbol': 'kg', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 1.0},
    {'name': 'Gram', 'symbol': 'g', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 0.001},
    {'name': 'Milligram', 'symbol': 'mg', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 0.000001},
    {'name': 'Pound', 'symbol': 'lb', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 0.453592},
    {'name': 'Ounce', 'symbol': 'oz', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 0.0283495},
    {'name': 'Quintal', 'symbol': 'qtl', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 100.0},
    {'name': 'Tonne', 'symbol': 'ton', 'unit_type': 'weight', 'supports_fractional': True, 'conversion_to_base': 1000.0},
    {'name': 'Liter', 'symbol': 'ltr', 'unit_type': 'volume', 'supports_fractional': True, 'conversion_to_base': 1.0},
    {'name': 'Milliliter', 'symbol': 'ml', 'unit_type': 'volume', 'supports_fractional': True, 'conversion_to_base': 0.001},
    {'name': 'Gallon', 'symbol': 'gal', 'unit_type': 'volume', 'supports_fractional': True, 'conversion_to_base': 3.78541},
    {'name': 'Meter', 'symbol': 'm', 'unit_type': 'length', 'supports_fractional': True, 'conversion_to_base': 1.0},
    {'name': 'Centimeter', 'symbol': 'cm', 'unit_type': 'length', 'supports_fractional': True, 'conversion_to_base': 0.01},
    {'name': 'Inch', 'symbol': 'in', 'unit_type': 'length', 'supports_fractional': True, 'conversion_to_base': 0.0254},
    {'name': 'Feet', 'symbol': 'ft', 'unit_type': 'length', 'supports_fractional': True, 'conversion_to_base': 0.3048},
    {'name': 'Yard', 'symbol': 'yd', 'unit_type': 'length', 'supports_fractional': True, 'conversion_to_base': 0.9144},
    {'name': 'Piece', 'symbol': 'pc', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Dozen', 'symbol': 'dz', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 12.0},
    {'name': 'Box', 'symbol': 'box', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Pack', 'symbol': 'pack', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Carton', 'symbol': 'ctn', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Pair', 'symbol': 'pr', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 2.0},
    {'name': 'Set', 'symbol': 'set', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Bundle', 'symbol': 'bnd', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Roll', 'symbol': 'roll', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Bag', 'symbol': 'bag', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Bottle', 'symbol': 'btl', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Can', 'symbol': 'can', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Tablet', 'symbol': 'tab', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Strip', 'symbol': 'strip', 'unit_type': 'count', 'supports_fractional': False, 'conversion_to_base': 1.0},
    {'name': 'Square Meter', 'symbol': 'sqm', 'unit_type': 'area', 'supports_fractional': True, 'conversion_to_base': 1.0},
    {'name': 'Square Feet', 'symbol': 'sqft', 'unit_type': 'area', 'supports_fractional': True, 'conversion_to_base': 0.092903},
]

def add_predefined_units(apps, schema_editor):
    ItemUnit = apps.get_model('pos', 'ItemUnit')
    for unit_data in PREDEFINED_UNITS:
        ItemUnit.objects.get_or_create(
            symbol=unit_data['symbol'],
            defaults=unit_data
        )

def remove_predefined_units(apps, schema_editor):
    ItemUnit = apps.get_model('pos', 'ItemUnit')
    symbols = [u['symbol'] for u in PREDEFINED_UNITS]
    ItemUnit.objects.filter(symbol__in=symbols).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('pos', '0034_global_units'),
    ]
    operations = [
        migrations.RunPython(add_predefined_units, remove_predefined_units),
    ]
