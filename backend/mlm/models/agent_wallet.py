#mlm/models/agent_wallet.py
from django.db import models
from users.models import User


class AgentWallet(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )

    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    updated_at = models.DateTimeField(auto_now=True)