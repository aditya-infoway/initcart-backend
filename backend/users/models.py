""" from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = (
        ('superadmin', 'Super Admin'),
        ('vendor', 'Vendor'),
        ('branch', 'Branch'),
        ('agent', 'Agent'),
        ('customer', 'Customer'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=15, blank=True, null=True)
    verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} ({self.role})"
class User(AbstractUser):
    ROLE_CHOICES = (
        ('superadmin', 'Super Admin'),
        ('vendor', 'Vendor'),
        ('branch', 'Branch'),
        ('agent', 'Agent'),
        ('customer', 'Customer'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=15, blank=True, null=True)
    verified = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Auto assign admin privileges
        if self.role == "superadmin":
            self.is_staff = True
            self.is_superuser = True

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"
 """


# users/models.py  ── Complete final version
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


# ─────────────────────────────────────────────────────────────────────────────
# Role choices  (module-level so migration can reference them)
# ─────────────────────────────────────────────────────────────────────────────

ROLE_CHOICES = [
    # ── existing roles (unchanged) ──
    ("customer",        "Customer Only"),
    ("agent",           "Agent Only"),
    ("both",            "Both Customer and Agent"),
    ("vendor",          "Vendor"),
    ("branch",          "Branch"),
    ("superadmin",      "Super Admin"),
    # ── new compound branch roles ──
    ("branch_customer", "Branch + Customer"),
    ("branch_agent",    "Branch + Agent"),
    ("branch_both",     "Branch + Customer + Agent"),
]

USER_TYPE_CHOICES = [
    # ── existing (unchanged) ──
    ("customer",        "Customer Only"),
    ("agent",           "Agent Only"),
    ("both",            "Both Customer and Agent"),
    ("vendor",          "Vendor"),
    ("branch",          "Branch"),
    ("superadmin",      "Super Admin"),
    # ── new compound branch roles ──
    ("branch_customer", "Branch + Customer"),
    ("branch_agent",    "Branch + Agent"),
    ("branch_both",     "Branch + Customer + Agent"),
]

# Role upgrade map (used by upgrade_role method)
ROLE_UPGRADE_MAP = {
    "branch":          {"customer": "branch_customer", "agent": "branch_agent"},
    "branch_customer": {"agent":    "branch_both"},
    "branch_agent":    {"customer": "branch_both"},
    "customer":        {"agent":    "both"},
    "agent":           {"customer": "both"},
}


# ─────────────────────────────────────────────────────────────────────────────
# User model
# ─────────────────────────────────────────────────────────────────────────────

class User(AbstractUser):
    # ── role constants (unchanged) ──
    ROLE_SUPERADMIN = "superadmin"
    ROLE_VENDOR     = "vendor"
    ROLE_BRANCH     = "branch"
    ROLE_AGENT      = "agent"
    ROLE_CUSTOMER   = "customer"
    ROLE_BOTH       = "both"

    email = models.EmailField(
        unique=True,
        null=True,    # agents jinka email nahi hai unke liye NULL allow
        blank=True,
    )
    # ── fields ──────────────────────────────────────────────────────────────
    role = models.CharField(
        max_length=30,                  # increased from 20 → 30 for 'branch_customer' etc.
        choices=ROLE_CHOICES,
        default=ROLE_CUSTOMER,
    )

    phone    = models.CharField(max_length=15, blank=True, null=True)
    verified = models.BooleanField(default=False)

    user_type = models.CharField(
        max_length=30,                  # increased from 20 → 30
        choices=USER_TYPE_CHOICES,
        default="customer",
    )

    referral_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    referred_by   = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
    )

    # ── save logic ───────────────────────────────────────────────────────────
    def save(self, *args, **kwargs):
        # Derive user_type from role (keep existing logic, add branch variants)
        if self.user_type != "both":
            if self.role == "agent":
                self.user_type = "agent"
            elif self.role in ("superadmin", "vendor", "branch"):
                self.user_type = self.role
            elif self.role == "both":
                self.user_type = "both"
            # ── NEW: branch compound roles keep same value for user_type ──
            elif self.role in ("branch_customer", "branch_agent", "branch_both"):
                self.user_type = self.role
            else:
                self.user_type = "customer"

        # Generate referral code for anyone who can act as agent
        if self.user_type in ("agent", "both", "branch_agent", "branch_both") \
                and not self.referral_code:
            self.referral_code = str(uuid.uuid4())[:8].upper()

        super().save(*args, **kwargs)

    # ── Role helpers ─────────────────────────────────────────────────────────

    def is_customer(self):
        """Can this user shop / access customer features?"""
        return self.role in (
            "customer",
            "both",
            "branch_customer",
            "branch_agent",    # branch+agent users can also shop
            "branch_both",
        )

    def is_agent(self):
        """Can this user access the agent panel?"""
        return self.role in (
            "agent",
            "both",
            "branch_agent",
            "branch_both",
        )

    def is_branch(self):
        """Is this user linked to a Branch franchise?"""
        return self.role in (
            "branch",
            "branch_customer",
            "branch_agent",
            "branch_both",
        )

    def is_superadmin(self):
        return self.role == "superadmin"

    def has_role(self, role_name):
        if self.user_type == "both":
            return True
        return self.role == role_name

    # ── Role upgrade utility ─────────────────────────────────────────────────

    def upgrade_role(self, add: str):
        new_role = ROLE_UPGRADE_MAP.get(self.role, {}).get(add)
        if new_role:
            self.role      = new_role
            self.user_type = new_role
            
            fields = ["role", "user_type"]
            
            # Generate referral_code if this upgrade grants agent capability
            # and the user doesn't already have one
            if not self.referral_code and new_role in ("agent", "both", "branch_agent", "branch_both"):
                self.referral_code = str(uuid.uuid4())[:8].upper()
                fields.append("referral_code")
            
            self.save(update_fields=fields)
        # if already has the capability → do nothing

    # ── String repr ─────────────────────────────────────────────────────────

    def __str__(self):
        return f"{self.username} ({self.user_type})"
    