from rest_framework import generics
from mlm.models.bank_details import AgentBankDetails
from mlm.serializers.bank_serializer import BankDetailsSerializer


class AddBankDetailsView(generics.CreateAPIView):

    serializer_class = BankDetailsSerializer


class BankDetailsView(generics.RetrieveAPIView):

    queryset = AgentBankDetails.objects.all()
    serializer_class = BankDetailsSerializer  