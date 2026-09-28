# Run: python manage.py shell < fix_mehir32_now.py
from decimal import Decimal
from django.db.models import Sum
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from ecommerce.models.order import OrderItem

agent = Agent.objects.get(user__email='mehir32@gmail.com')  # exact email daal dena
print("Before:", agent.total_sales, agent.is_active_agent)

delivered_total = OrderItem.objects.filter(
    order__customer=agent.user, item_status="delivered"
).aggregate(total=Sum('total_price'))['total'] or Decimal('0')

agent.total_sales = delivered_total
settings_obj = MLMSettings.objects.first()
if agent.total_sales < settings_obj.minimum_sale_amount:
    agent.is_active_agent = False
    agent.minimum_achieved_at = None
    agent.minimum_achieved_order = None

agent.save()
print("After:", agent.total_sales, agent.is_active_agent)