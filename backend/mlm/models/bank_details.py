from django.db import models
from mlm.models.agent import Agent


class AgentBankDetails(models.Model):

    agent = models.OneToOneField(
        Agent,
        on_delete=models.CASCADE,
        related_name="bank_details"
    )

    bank_name = models.CharField(max_length=255)

    account_number = models.CharField(max_length=50)

    ifsc_code = models.CharField(max_length=20)

    upi_id = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.agent.full_name} Bank"