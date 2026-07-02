from django.contrib import admin
from ecommerce.models.loyalty import LoyaltyPointsConfig, LoyaltyPointsTransaction
from ecommerce.models.subscription import SubscriptionPlan
from ecommerce.models.vendor import (
    Vendor, VendorApprovalRequest, VendorWallet,
    VendorWithdrawalRequest, Brand
)

# =========================================================
#  VENDOR ADMIN
# =========================================================
@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'business_name', 'vendor_type', 'owner_name',
        'email', 'phone', 'status', 'verification_label', 'is_approved', 'created_at'
    )
    search_fields = ('business_name', 'owner_name', 'email', 'phone')
    list_filter = ('status', 'vendor_type', 'verification_label')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ("Basic Info", {
            "fields": (
                "business_name", "vendor_type","vendor_subtype", 
                "owner_name", "email", "phone", "address",
                "city", "state", "pincode"
            )
        }),
        ("Documents", {
            "fields": ("licence_file", "gst_certificate", "id_proof")
        }),
        ("Bank Details (Admin Only)", {
            "fields": ("bank_name", "account_number", "ifsc_code", "upi_id")
        }),
        ("Status", {
            "fields": ("status", "verification_label", "is_approved", "created_at", "updated_at")
        }),
    )


# =========================================================
#  VENDOR APPROVAL REQUEST ADMIN
# =========================================================
@admin.register(VendorApprovalRequest)
class VendorApprovalAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'vendor_name', 'vendor_email', 'date', 'status')
    search_fields = ('request_id', 'vendor__business_name', 'vendor__email')
    list_filter = ('status', 'date')
    readonly_fields = ('request_id', 'date')

    def vendor_name(self, obj):
        return obj.vendor.business_name
    vendor_name.short_description = "Vendor Name"

    def vendor_email(self, obj):
        return obj.vendor.email
    vendor_email.short_description = "Email"


# =========================================================
#  WALLET ADMIN
# =========================================================
@admin.register(VendorWallet)
class VendorWalletAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'wallet_balance', 'total_earnings', 'pending_balance', 'updated_at')
    search_fields = ('vendor__business_name', 'vendor__email')
    readonly_fields = ('updated_at',)


# =========================================================
#  WITHDRAWAL ADMIN
# =========================================================
@admin.register(VendorWithdrawalRequest)
class VendorWithdrawalAdmin(admin.ModelAdmin):
    list_display = (
        'request_id', 'vendor', 'requested_amount', 'status',
        'payment_mode', 'request_date', 'paid_date'
    )
    search_fields = ('request_id', 'vendor__business_name', 'vendor__email')
    list_filter = ('status', 'payment_mode')
    readonly_fields = ('request_date',)


# =========================================================
#  BRAND ADMIN
# =========================================================
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('brand_name', 'status', 'created_at')
    search_fields = ('brand_name',)
    list_filter = ('status',)
    readonly_fields = ('created_at', 'updated_at')



@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['service_type', 'subscription_type', 'amount', 'is_active', 'created_at']
    list_filter = ['service_type', 'subscription_type', 'is_active']
    search_fields = ['service_type', 'subscription_type', 'description']
    list_editable = ['is_active', 'amount']

@admin.register(LoyaltyPointsConfig)
class LoyaltyPointsConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'points_type', 'is_active', 'priority', 'valid_from', 'valid_to']
    list_filter = ['points_type', 'is_active', 'earned_on']
    search_fields = ['name', 'description']
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'points_type', 'earned_on', 'is_active', 'priority')
        }),
        ('Points Configuration', {
            'fields': ('percentage_rate', 'fixed_points', 
                      'min_amount', 'max_amount', 'tier_points'),
            'classes': ('collapse',)
        }),
        ('Conditions', {
            'fields': ('min_order_amount', 'max_points_per_order'),
            'classes': ('collapse',)
        }),
        ('Validity', {
            'fields': ('valid_from', 'valid_to'),
            'classes': ('collapse',)
        }),
    )

@admin.register(LoyaltyPointsTransaction)
class LoyaltyPointsTransactionAdmin(admin.ModelAdmin):
    list_display = ['customer', 'points', 'transaction_type', 'balance_after', 'created_at']
    list_filter = ['transaction_type', 'created_at']
    search_fields = ['customer__username', 'customer__email', 'description']
    readonly_fields = ['balance_after', 'created_at']
