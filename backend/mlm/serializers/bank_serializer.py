from rest_framework import serializers
from mlm.models.bank_details import AgentBankDetails


class BankDetailsSerializer(serializers.ModelSerializer):

    class Meta:
        model = AgentBankDetails
        fields = "__all__"