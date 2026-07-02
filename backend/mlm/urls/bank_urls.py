from django.urls import path
from mlm.views.bank_views import *

urlpatterns = [

    path("bank/add/", AddBankDetailsView.as_view()),

    path("bank/<int:pk>/", BankDetailsView.as_view()),
]