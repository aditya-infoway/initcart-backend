from django.urls import path

from mlm.views.agent_dashboard_views import AgentDashboardAPIView
from mlm.views.upline_views import AgentUplineAPIView
from mlm.views.downline_views import AgentDownlineAPIView
from mlm.views.sales_graph_views import AgentMonthlySalesAPIView
from mlm.views.commission_report_views import AgentCommissionReportAPIView

from mlm.views.admin_commission_views import AdminMLMOverviewAPIView, AdminAgentCommissionDetailAPIView


urlpatterns = [

    path("dashboard/", AgentDashboardAPIView.as_view()),

    path("upline/", AgentUplineAPIView.as_view()),

    path("downline/", AgentDownlineAPIView.as_view()),

    path("sales-graph/", AgentMonthlySalesAPIView.as_view()),

    path("commission-report/", AgentCommissionReportAPIView.as_view()),
    
    path('admin/mlm-overview/',              AdminMLMOverviewAPIView.as_view()),
    path('admin/agent-commission/<int:agent_id>/', AdminAgentCommissionDetailAPIView.as_view()),

]