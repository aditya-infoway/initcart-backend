#core/urls.py(main urls)
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from ecommerce.urls.service_urls import urlpatterns as service_urls
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from users.views import handler429

handler429 = handler429 

urlpatterns = [
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

urlpatterns = [
    path("admin/", admin.site.urls),

    # User Authentication (Login, Register APIs)
    path("api/auth/", include("users.urls")),

    #  Ecommerce Vendor APIs (All vendor,,vendor requests  and approvals for  this urls use this for all  approvals  brand, wallet, withdrawal endpoints)
    path("api/ecommerce/", include("ecommerce.urls.vendor_urls")),

    #public urls
    path("ecommerce/",include("ecommerce.urls.public_urls")),
    
    # Optional: DRF’s browsable API login/logout (useful in admin testing)
    path("api/rest-auth/", include("rest_framework.urls")),

    #category master urls for all category
    path("api/ecommerce/" , include("ecommerce.urls.category_urls")),

    #campaign
    path("api/ecommerce/", include("ecommerce.urls.campaign_urls")),

    #product all urls
    path("api/ecommerce/",include("ecommerce.urls.product_urls")),

    #customer urls
    path("ecommerce/", include("ecommerce.urls.customer_urls")),

    #order & urls 
    path('api/public/', include('ecommerce.urls.order_urls')),

    # Loyalty points management for customer
    path("api/ecommerce/", include("ecommerce.urls.loyalty_urls")),
    #coupons for ecommerce 
    path("api/ecommerce/", include("ecommerce.urls.coupon_urls")),
    #vendor_orderurls
    path('api/ecommerce/', include('ecommerce.urls.vendor_order_urls')),
    #subscription urls
    path("api/ecommerce/", include("ecommerce.urls.subscription_urls")),

    #POS (branch)
    path("api/pos/" , include("pos.urls.branch_urls")),
    path("api/banners/", include("banners.urls")),
        #POS (branch)
    path("api/pos/"  , include("pos.urls.account_urls")),
    path("api/pos/" , include("pos.urls.item_urls")),
    path("api/pos/" , include("pos.urls.purchaseentry_urls")),
    path("api/pos/" , include("pos.urls.purchasereturn_urls")),
    path("api/pos/" , include("pos.urls.salesentry_urls")),
    path("api/pos/" , include("pos.urls.stockreport_urls")),
    path("api/pos/" , include("pos.urls.bankpayment_urls")),
    path("api/pos/" , include("pos.urls.cashpayment_urls")),
    path("api/pos/" , include("pos.urls.bankreceipt_urls")),
    path("api/pos/" , include("pos.urls.cashreceipt_urls")),
    path("api/pos/" , include("pos.urls.settings_urls")),
    path("api/pos/" , include("pos.urls.contra_urls")),
    path("api/pos/" , include("pos.urls.journalentries_urls")),
    path("api/pos/" , include("pos.urls.LedgerReport_urls")),
    path("api/pos/" , include("pos.urls.dashboard_urls")),
    path("api/pos/", include("pos.urls.salesreturn_urls")),
    path('api/pos/', include('pos.urls.stock_transfer_urls')),
    path('api/pos/', include("pos.urls.branch_order_urls")),
    path('api/pos/', include("pos.urls.pos_mlm_urls")),
    path('api/pos/', include("pos.urls.stock_return_urls")),
    # Super Admin Order Management  
    path('api/ecommerce/', include('ecommerce.urls.superadmin_order_urls')),
    
    # services - ADD THIS LINE
    path("api/ecommerce/services/", include("ecommerce.urls.service_urls")),
    
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path("api/public/" ,  include("ecommerce.urls.webhook_urls")),
    
        # services - ADD THIS LINE
    path("api/ecommerce/services/", include("ecommerce.urls.service_urls")),
    path("api/", include("services.urls.main_urls")),
    path("api/", include("services.urls.banners_urls")),
    path('services/', include('services.urls.public_urls')),
    path('api/', include('services.urls.review_urls')),

    
    ########## M L M ###########
    
    path("api/mlm/", include("mlm.urls.profit_distribution_urls")),
    path("api/mlm/", include("mlm.urls.mlm_level_urls")),
    path("api/mlm/", include("mlm.urls.agent_urls")),
    path("api/mlm/", include("mlm.urls.bank_urls")),
    path("api/mlm/", include("mlm.urls.tree_urls")),
    path("api/mlm/", include("mlm.urls.mlm_settings_urls")),
    path("api/mlm/", include("mlm.urls.dashboard_urls")),
    path("api/mlm/", include("mlm.urls.sales_urls")),
    
    
]

# For serving uploaded media files in dev mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    