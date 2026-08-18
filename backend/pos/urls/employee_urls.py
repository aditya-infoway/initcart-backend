# apni urls.py 
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from pos.views.employee_views import EmployeeViewSet, EmployeePermissionView

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')

urlpatterns = [

    path('', include(router.urls)),
    path('employees/<int:employee_id>/permissions/', EmployeePermissionView.as_view(), name='employee-permissions'),
]