from django.urls import path

from mlm.views.agent_sales_views import AgentSalesAPIView
from mlm.views.admin_sales_views import AdminMLMSalesAPIView
from mlm.views.admin_agents_sales_views import AdminAgentSalesAPIView


urlpatterns = [

    path("agent/sales/", AgentSalesAPIView.as_view()),

    path("admin/mlm-sales/", AdminMLMSalesAPIView.as_view()),

    path("admin/agent-sales/<int:agent_id>/", AdminAgentSalesAPIView.as_view()),

]