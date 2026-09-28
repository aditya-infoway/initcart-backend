# Run: python manage.py shell < debug_mehir33.py
from decimal import Decimal
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from ecommerce.models.order import Order, OrderItem

agent = Agent.objects.get(user__email='mehir32@gmail.com')
print("Agent:", agent.full_name)
print("total_sales:", agent.total_sales)
print("is_active_agent:", agent.is_active_agent)
print("minimum_achieved_at:", agent.minimum_achieved_at)
print("minimum_achieved_order_id:", agent.minimum_achieved_order_id)

settings_obj = MLMSettings.objects.first()
print("minimum_sale_amount:", settings_obj.minimum_sale_amount)

# Actual delivered items sum kya hai — DB truth
delivered_total = OrderItem.objects.filter(
    order__customer=agent.user,
    item_status="delivered",
).aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('total_price'))['total'] or Decimal('0')
print("\nActual sum of delivered order-items for this customer:", delivered_total)
print("(agar yeh agent.total_sales se zyada hai, matlab sync signal chala hi nahi)")

print("\nRecent orders for this customer:")
for o in Order.objects.filter(customer=agent.user).order_by('-created_at')[:5]:
    print(f"  {o.order_number} | order_status={o.order_status}")
    for it in o.items.all():
        print(f"     item={it.id} | item_status={it.item_status} | "
              f"total_price={it.total_price} | mlm_commission_processed={it.mlm_commission_processed} | "
              f"platform_profit={it.platform_profit}")