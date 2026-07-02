from django.urls import path
from mlm.views.agent_views import *
from mlm.views.agent_eligibilit_views import AgentEligibilityCheckAPIView

urlpatterns = [

    path("register/", AgentRegisterView.as_view()),

    path("agents/", AgentListView.as_view()),

    path("approve-agent/<int:id>/", AgentApproveView.as_view()),
    
    path("login/", AgentLoginView.as_view()),
    
    path("agent/profile/", AgentProfileView.as_view()), 

    path("agents/<int:id>/", AgentDetailView.as_view()),
    
    path('agents/check-eligibility/', AgentEligibilityCheckAPIView.as_view(), name='agent-eligibility'),
    
       
    path('agents/<int:pk>/upload-documents/', 
         AgentDocumentUploadView.as_view(), name='agent-document-upload'),
]