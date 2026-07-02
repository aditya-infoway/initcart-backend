# mlm/urls/tree_urls.py
from django.urls import path
from mlm.views.tree_views import (
    AgentDownlineTreeAPIView,
    AgentDirectDownlinesAPIView,
    AdminAgentTreeAPIView,
)
from mlm.views.hierarchy_views import (
    DownlineHierarchyAPIView,
    UplineHierarchyAPIView,
    UplineTreeAPIView,  # Add this
)

urlpatterns = [
    path("tree/", AgentDownlineTreeAPIView.as_view()),
    path("direct-downlines/", AgentDirectDownlinesAPIView.as_view()),
    path("admin-tree/", AdminAgentTreeAPIView.as_view()),
    
    # Hierarchy endpoints
    path("hierarchy/downline/", DownlineHierarchyAPIView.as_view(), name="downline-hierarchy"),
    path("hierarchy/upline/", UplineHierarchyAPIView.as_view(), name="upline-hierarchy"),
    path("hierarchy/upline-tree/", UplineTreeAPIView.as_view(), name="upline-tree"),  # Add this
]