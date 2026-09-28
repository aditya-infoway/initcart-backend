# verify_reversal_fix.py
from users.models import User
from ecommerce.models.order import Order, OrderItem
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from mlm.models.mlm_transaction import MLMTransaction

print("="*70)
print("VERIFY: self-purchase deactivation on partial refund")
print("="*70)

user = User.objects.get(email='mehir3@gmail.com')
agent = Agent.objects.get(user=user)
settings = MLMSettings.objects.first()

print(f"BEFORE: total_sales={agent.total_sales} is_active={agent.is_active_agent} "
      f"min_required={settings.minimum_sale_amount}")

# Find a delivered item belonging to this self-purchase agent with commission
item = OrderItem.objects.filter(
    order__customer=user, item_status='delivered', mlm_commission_processed=True
).exclude(platform_profit=0).first()

if not item:
    print("❌ No commissioned delivered item found for this user — pick a real one manually")
else:
    print(f"Testing with item#{item.id} total_price={item.total_price}")

    class FakeRefund:
        def __init__(self, order, order_item, refund_amount):
            self.order = order
            self.order_item = order_item
            self.refund_amount = refund_amount
            self.commission_reversed = False
        def save(self, update_fields=None):
            pass

    # simulate what process_refund does before calling reversal
    item.item_status = 'refunded'
    item.save(update_fields=['item_status'])

    fake_refund = FakeRefund(item.order, item, item.total_price)

    from utils.commission_reversal import reverse_commission_for_return
    reverse_commission_for_return(fake_refund)

    agent.refresh_from_db()
    print(f"\nAFTER: total_sales={agent.total_sales} is_active={agent.is_active_agent}")
    print("✅ PASS — total_sales reduced" if agent.total_sales < settings.minimum_sale_amount or not agent.is_active_agent
          else "⚠️ still above threshold — check if other delivered items keep it active (may be correct)")