# ============================================================
# FILE: pos/models/pos_profit_settings.py
# ACTION: CREATE this new file
# ============================================================
# PURPOSE:
#   POS branch ke liye walk-in toggle store karna.
#   Superadmin yahan se toggle ON/OFF kar sakta hai.
#
#   Toggle ON  → simple 90/10 split (walk-in customers)
#   Toggle OFF → MLM distribution (referral code based)
# ============================================================

from django.db import models


class POSProfitSettings(models.Model):
    """
    Singleton model — sirf ek record rahega.
    Superadmin panel se update hoga.
    """

    # True  = Walk-in mode  → 90% branch, 10% company (no MLM)
    # False = MLM mode      → ProfitDistribution config use hoga
    walk_in_toggle = models.BooleanField(
        default=True,
        help_text=(
            "ON = Walk-in simple split (90% branch, 10% company). "
            "OFF = MLM distribution mode (referral code required)."
        ),
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "POS Profit Settings"
        verbose_name_plural = "POS Profit Settings"

    def __str__(self):
        mode = "Walk-in (90/10)" if self.walk_in_toggle else "MLM Distribution"
        return f"POS Profit Mode: {mode}"

    @classmethod
    def get_toggle(cls):
        """
        Helper: toggle value nikalo.
        Agar settings exist nahi karta toh default True return karo.
        """
        obj = cls.objects.first()
        if obj is None:
            return True   # default: simple walk-in mode
        return obj.walk_in_toggle
    
    