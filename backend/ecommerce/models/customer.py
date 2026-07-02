# ecommerce/models/customer.py  (complete updated file)
# Changes from original:
#   - check_agent_eligibility()            → no change in logic; branch users flow through the same path
#   - create_agent_profile_from_customer() → calls user.upgrade_role('agent') for branch users
#   - save()                               → unchanged
# Everything else is identical to your original.

from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from mlm.models.mlm_settings import MLMSettings
from users.models import User
from django.utils import timezone
from datetime import timedelta
import random


class CustomerProfile(models.Model):
    user      = models.OneToOneField(User, on_delete=models.CASCADE, related_name="customer_profile")
    full_name = models.CharField(max_length=255)
    phone     = models.CharField(max_length=15)
    email     = models.EmailField()
    address   = models.TextField()
    city      = models.CharField(max_length=100)
    state     = models.CharField(max_length=100)

    total_orders = models.PositiveIntegerField(default=0)
    total_spent  = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    loyalty_points = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Agent eligibility
    is_eligible_for_agent      = models.BooleanField(default=False)
    eligible_for_agent_since   = models.DateTimeField(null=True, blank=True)

    # Document upload tracking
    agent_documents_uploaded    = models.BooleanField(default=False)
    agent_documents_uploaded_at = models.DateTimeField(null=True, blank=True)

    # Temp document storage
    passport_photo_temp = models.ImageField(upload_to="temp/agents/photos/", null=True, blank=True)
    id_proof_temp       = models.FileField(upload_to="temp/agents/idproof/",  null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "email"], name="unique_user_email")
        ]

    # ─────────────────────────────────────────────────────────────────────
    def check_agent_eligibility(self):
        """Check if customer (including branch-customer) is eligible to become an agent."""
        from ecommerce.models.order import Order
        from django.db.models import Sum

        delivered_orders   = Order.objects.filter(customer=self.user, order_status="delivered")
        actual_total_spent = delivered_orders.aggregate(total=Sum("final_amount"))["total"] or Decimal("0.00")

        if self.total_spent != actual_total_spent:
            self.total_spent = actual_total_spent
            self.save(update_fields=["total_spent"])

        settings = MLMSettings.objects.first()
        if not settings:
            return False

        min_amount = settings.minimum_sale_amount

        if self.total_spent >= min_amount:
            if not self.is_eligible_for_agent:
                self.is_eligible_for_agent     = True
                self.eligible_for_agent_since  = timezone.now()
                self.save(update_fields=["is_eligible_for_agent", "eligible_for_agent_since"])
                self.notify_agent_eligibility()
            return True
        else:
            if self.is_eligible_for_agent:
                self.is_eligible_for_agent = False
                self.save(update_fields=["is_eligible_for_agent"])
            return False

    # ─────────────────────────────────────────────────────────────────────
    def create_agent_profile_from_customer(
        self,
        passport_photo=None,
        id_proof=None,
        gst_certificate=None,
        business_license=None,
        agent_type="normal",
        society_or_business_name="",
    ):
        """
        Create (or update) an Agent record from this customer profile.
        Works for regular customers AND branch-customers.
        """
        from mlm.models.agent import Agent

        # ── Update existing agent if present ───────────────────────────────
        if Agent.objects.filter(user=self.user).exists():
            agent = Agent.objects.get(user=self.user)
            if passport_photo:   agent.passport_photo   = passport_photo
            if id_proof:         agent.id_proof         = id_proof
            if gst_certificate:  agent.gst_certificate  = gst_certificate
            if business_license: agent.business_license = business_license
            agent.status          = "approved"
            agent.is_active_agent = True
            agent.save()
            return agent

        # ── Create new agent ───────────────────────────────────────────────
        agent = Agent.objects.create(
            user                    = self.user,
            agent_type              = agent_type,
            full_name               = self.full_name,
            contact_number          = getattr(self.user, "phone", None) or self.phone,
            email                   = self.user.email or self.email,
            address                 = self.address,
            city                    = self.city,
            state                   = self.state,
            society_or_business_name= society_or_business_name,
            status                  = "pending",
            is_active_agent         = True,
            total_sales             = self.total_spent,
            minimum_achieved_at     = timezone.now(),
            created_by              = None,
            passport_photo          = passport_photo,
            id_proof                = id_proof,
            gst_certificate         = gst_certificate,
            business_license        = business_license,
        )

        # Mark documents uploaded
        self.agent_documents_uploaded    = True
        self.agent_documents_uploaded_at = timezone.now()
        self.save()

        # ── Role upgrade ────────────────────────────────────────────────────
        # Uses the upgrade_role() helper defined in users/models_patch.py
        # Regular customer  → 'both'
        # Branch customer   → 'branch_both'   (via upgrade_role('agent'))
        # Branch (no shop)  → 'branch_agent'  (via upgrade_role('agent'))
        self.user.upgrade_role("agent")

        self.send_agent_activation_email(agent)
        return agent

    # ─────────────────────────────────────────────────────────────────────
    def send_agent_activation_email(self, agent):
        try:
            from django.core.mail import send_mail
            from django.conf import settings as django_settings

            send_mail(
                subject="🎉 Congratulations! Your Agent Account is Active!",
                message=f"""
Hello {self.full_name},

Great news! Your agent account has been activated successfully!

Agent Details:
- Agent ID: AG-{agent.id}
- Agent Type: {agent.get_agent_type_display()}
- Status: Active

You can now login to the agent panel using your existing credentials.

Best regards,
Ecommerce Store Team
""",
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"Email error: {e}")

    # ─────────────────────────────────────────────────────────────────────
    def notify_agent_eligibility(self):
        try:
            from django.core.mail import send_mail
            from django.conf import settings as django_settings

            send_mail(
                subject=" You're Eligible to Become an Agent!",
                message=f"""
Hello {self.full_name},

Congratulations! You've reached the minimum purchase amount and are now eligible to become an agent!

To activate your agent account, please upload:
1. Passport Size Photo
2. ID Proof (Aadhar/PAN Card)

Login to your profile and click on "Become an Agent" to upload documents.

Best regards,
Ecommerce Store Team
""",
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.email],
                fail_silently=True,
            )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────
    def __str__(self):
        return f"{self.full_name} - {self.email}"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def loyalty_points_balance(self):
        return self.loyalty_points

    @property
    def available_points_value(self):
        return (self.loyalty_points / 100) * 10


# ─────────────────────────────────────────────────────────────────────────────
class PasswordResetOTP(models.Model):
    """OTP model for password resets"""
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_otps")
    otp        = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=timezone.now)
    is_used    = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.pk:
            self.otp        = str(random.randint(100000, 999999))
            self.expires_at = timezone.now() + timedelta(minutes=10)
        super().save(*args, **kwargs)

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    def __str__(self):
        return f"OTP for {self.user.email}: {self.otp}"

    class Meta:
        verbose_name        = "Password Reset OTP"
        verbose_name_plural = "Password Reset OTPs"