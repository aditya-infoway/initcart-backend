# Run: python manage.py shell < debug_next_order_commission.py
from decimal import Decimal
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from mlm.models.mlm_transaction import MLMTransaction
from ecommerce.models.order import Order, OrderItem

# ✅ apna agent email yahan daal do
agent = Agent.objects.get(user__email='PASTE_AGENT_EMAIL_HERE')

print("=== AGENT STATE ===")
print("full_name:", agent.full_name)
print("total_sales:", agent.total_sales)
print("is_active_agent:", agent.is_active_agent)
print("minimum_achieved_at:", agent.minimum_achieved_at)
print("minimum_achieved_order_id:", agent.minimum_achieved_order_id)

settings_obj = MLMSettings.objects.first()
print("minimum_sale_amount:", settings_obj.minimum_sale_amount)

print("\n=== RECENT ORDERS (is agent ke referral/self) ===")
orders = Order.objects.filter(referral_agent=agent).order_by('created_at')
for o in orders:
    print(f"\n  Order {o.id} | {o.order_number} | status={o.order_status} | "
          f"mlm_commission_processed={o.mlm_commission_processed}")
    for it in o.items.all():
        print(f"     item={it.id} | status={it.item_status} | "
              f"total_price={it.total_price} | platform_profit={it.platform_profit} | "
              f"mlm_commission_processed={it.mlm_commission_processed}")

print("\n=== MLM TRANSACTIONS for this seller (as recipient) ===")
for tx in MLMTransaction.objects.filter(user=agent.user).order_by('created_at'):
    print(f"  order={tx.order_id} | order_item={tx.order_item_id} | "
          f"level={tx.level} | amount={tx.amount} | type={tx.transaction_type} | "
          f"created_at={tx.created_at}")

print("\n=== MANUAL is_agent_active() TEST ===")
from utils.agent_status import is_agent_active

# Sabse naya order lo (jo achieving order ke BAAD ka hai)
latest_order = orders.last()
if latest_order:
    print(f"Testing is_agent_active for latest order: {latest_order.order_number} (id={latest_order.id})")
    print("Result:", is_agent_active(agent.user, current_order=latest_order))
    print("Comparison check:")
    print("  agent.minimum_achieved_order_id:", agent.minimum_achieved_order_id)
    print("  latest_order.id:", latest_order.id)
    print("  Are they equal?:", agent.minimum_achieved_order_id == latest_order.id)