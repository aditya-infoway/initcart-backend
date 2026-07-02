# mlm/models/agent.py (Update the can_refer_agents method)
import uuid
from django.db import models
from django.conf import settings
from users.models import User


class Agent(models.Model):

    AGENT_TYPE = (
        ("normal", "Normal Agent"), 
        ("pos", "POS Agent"),
        ("society", "Society Agent"),
    )

    STATUS = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active_agent = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='agents_created'
    )

    agent_type = models.CharField(max_length=20, choices=AGENT_TYPE)

    full_name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=15)
    email = models.EmailField()

    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)

    society_or_business_name = models.CharField(
        max_length=255, blank=True, null=True
    )

    status = models.CharField(max_length=20, choices=STATUS, default="pending")

    passport_photo = models.ImageField(upload_to="agents/photos/")
    id_proof = models.FileField(upload_to="agents/idproof/")

    gst_certificate = models.FileField(upload_to="agents/gst/", blank=True, null=True)
    business_license = models.FileField(upload_to="agents/license/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    minimum_achieved_at = models.DateTimeField(null=True, blank=True)
    
    is_pos_branch_agent = models.BooleanField(
        default=False,
        help_text=(
            "True = auto-created from POS branch signal (already eligible). "
            "False = manually registered POS agent (normal rules apply)."
        ),
    )
    
    minimum_achieved_order = models.ForeignKey(
        'ecommerce.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='minimum_achieving_agents'
    )
    def __str__(self):
        return self.full_name
    
    def has_minimum_sales(self):
        """
        POS branch agent (signal se bana): always True — no minimum needed.
        Manually registered POS / Normal / Society: check total_sales.
        """
        #  Sirf branch signal se bane POS agents ko bypass milega
        if self.agent_type == "pos" and self.is_pos_branch_agent:
            return True
    
        from mlm.models.mlm_settings import MLMSettings
        settings = MLMSettings.objects.first()
        if not settings:
            return False
    
        return self.total_sales >= settings.minimum_sale_amount
    
    def add_sales(self, amount):
        """Add sales amount to agent's total_sales (poore order ka amount)"""
        from decimal import Decimal
        amount = Decimal(str(amount))
        if amount > 0:
            self.total_sales = self.total_sales + amount
            self.save(update_fields=['total_sales'])
            print(f"  ✅ Agent {self.full_name} total_sales: +₹{amount} = ₹{self.total_sales}")
            return True
        return False
    
    def can_refer_agents(self):
        """
        POS branch agent: sirf approved + active check.
        Manual POS / Normal / Society: minimum sales bhi check.
        """
        if self.status != "approved":
            return False, "Agent not approved yet"

        # ✅ Branch signal se bane POS agents: no minimum sales check
        if self.agent_type == "pos" and self.is_pos_branch_agent:
            if self.is_active_agent:
                return True, "POS Branch Agent — always eligible"
            return False, "POS Branch Agent not active"

        # Manually registered agents: minimum sales + active check
        if not self.is_active_agent:
            return False, "Agent is not active"

        from mlm.models.mlm_settings import MLMSettings
        settings = MLMSettings.objects.first()
        if not settings:
            return False, "MLM settings not configured"

        if self.total_sales < settings.minimum_sale_amount:
            return False, (
                f"Minimum sales not met. "
                f"Need ₹{settings.minimum_sale_amount}, "
                f"have ₹{self.total_sales}"
            )

        return True, "Eligible to refer agents"
    
    
    def is_eligible_for_commission(self, order_date=None):
        """
        POS branch agent: always eligible.
        Others: only after minimum_achieved_at.
        """
        if not self.is_active_agent:
            return False
    
        # ✅ Branch signal se bane POS agents
        if self.agent_type == "pos" and self.is_pos_branch_agent:
            return True
    
        if not self.minimum_achieved_at:
            return False
    
        if order_date and self.minimum_achieved_at:
            return order_date >= self.minimum_achieved_at
    
        return True