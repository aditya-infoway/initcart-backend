# ecommerce/utils/payment_helpers.py
from decimal import Decimal
from ecommerce.models.order import OrderItem, VendorDeliveryInfo
from ecommerce.models.payment_request import VendorCODRecovery
from datetime import timedelta
from django.utils import timezone
from django.db import models


def get_item_platform_charge(item: OrderItem) -> Decimal:
    """Platform charge amount for a single order item."""
    pct = Decimal('0.00')
    if item.product_stock and item.product_stock.platform_charge_percent:
        pct = item.product_stock.platform_charge_percent
    elif item.product and item.product.category:
        pct = item.product.category.platform_charge

    if not pct or pct <= 0:
        return Decimal('0.00')

    return round((item.total_price * pct) / Decimal('100'), 2)


def _apply_date_range(qs, date_from, date_to):
    if date_from:
        qs = qs.filter(order__created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(order__created_at__date__lte=date_to)
    return qs


def get_vendor_eligible_online_orders(vendor, date_from=None, date_to=None):
    """
    Online (razorpay), delivered orders for this vendor within the date range.
    Excludes:
      - orders currently sitting in a PENDING request (awaiting admin decision)
      - orders that were ACTUALLY APPROVED in some approved/paid request
    Orders that were part of a request but did NOT get approved (partial
    approval leftovers) become eligible again automatically.
    """
    from ecommerce.models.payment_request import VendorPaymentRequest

    # 1) Orders stuck in a pending request — don't let vendor re-select these
    #    while a decision is still awaited.
    pending_order_ids = VendorPaymentRequest.objects.filter(
        vendor=vendor, status='pending'
    ).values_list('orders__id', flat=True)

    # 2) Orders that were actually approved (and optionally paid) — these are
    #    done, permanently excluded.
    approved_order_ids = VendorPaymentRequest.objects.filter(
        vendor=vendor, status__in=['approved', 'paid']
    ).values_list('approved_orders__id', flat=True)

    excluded_order_ids = set(pending_order_ids) | set(approved_order_ids)
    excluded_order_ids.discard(None)

    items = OrderItem.objects.filter(
        vendor=vendor,
        order__payment_method='razorpay',
        order__order_status='delivered',
    ).exclude(order_id__in=excluded_order_ids)

    items = _apply_date_range(items, date_from, date_to)
    items = items.select_related('order', 'product_stock', 'product').order_by('-order__created_at')

    orders_map = {}
    for item in items:
        order = item.order
        charge = get_item_platform_charge(item)
        if order.id not in orders_map:
            orders_map[order.id] = {
                'order_id': order.id,
                'order_number': order.order_number,
                'created_at': order.created_at,
                'billing_name': order.billing_name,
                'vendor_total': Decimal('0.00'),
                'platform_charge': Decimal('0.00'),
            }
        orders_map[order.id]['vendor_total'] += item.total_price
        orders_map[order.id]['platform_charge'] += charge

    result = []
    for data in orders_map.values():
        data['net_amount'] = data['vendor_total'] - data['platform_charge']
        result.append(data)
    return result

def get_vendor_cod_platform_charge(vendor, date_from=None, date_to=None):
    """
    Total platform charge to recover from COD + self-delivery, delivered
    orders (vendor already collected this money directly) within the range,
    excluding items already recovered in a previous non-rejected request.
    Returns (total_charge: Decimal, item_charges: list[(OrderItem, Decimal)]).
    """
    recovered_ids = VendorCODRecovery.objects.filter(
        order_item__vendor=vendor
    ).values_list('order_item_id', flat=True)

    self_delivery_order_ids = VendorDeliveryInfo.objects.filter(
        vendor=vendor, delivery_service='self'
    ).values_list('order_id', flat=True)

    items = OrderItem.objects.filter(
        vendor=vendor,
        order__payment_method='cod',
        order__order_status='delivered',
        order_id__in=list(self_delivery_order_ids),
    ).exclude(id__in=list(recovered_ids))

    items = _apply_date_range(items, date_from, date_to)
    items = items.select_related('product_stock', 'product', 'order')

    total = Decimal('0.00')
    item_charges = []
    for item in items:
        charge = get_item_platform_charge(item)
        if charge > 0:
            total += charge
            item_charges.append((item, charge))

    return total, item_charges


def get_order_summaries(vendor, order_ids):
    """Per-order vendor_total + platform_charge for a specific set of order ids."""
    items = OrderItem.objects.filter(
        vendor=vendor, order_id__in=order_ids
    ).select_related('order', 'product_stock', 'product')

    orders_map = {}
    for item in items:
        order = item.order
        charge = get_item_platform_charge(item)
        if order.id not in orders_map:
            orders_map[order.id] = {
                'order_id': order.id,
                'order_number': order.order_number,
                'created_at': order.created_at,
                'billing_name': order.billing_name,
                'vendor_total': Decimal('0.00'),
                'platform_charge': Decimal('0.00'),
            }
        orders_map[order.id]['vendor_total'] += item.total_price
        orders_map[order.id]['platform_charge'] += charge

    return list(orders_map.values())




def get_vendor_order_report(vendor, date_from=None, date_to=None, search=None):
    """
    Full order-level report for a SINGLE vendor.
    """
    items = OrderItem.objects.filter(vendor=vendor).select_related(
        'order', 'product_stock', 'product'
    )

    if date_from:
        items = items.filter(order__created_at__date__gte=date_from)
    if date_to:
        items = items.filter(order__created_at__date__lte=date_to)

    if search:
        items = items.filter(
            models.Q(order__order_number__icontains=search) |
            models.Q(order__billing_name__icontains=search) |
            models.Q(order__billing_phone__icontains=search) |
            models.Q(order__billing_email__icontains=search)
        )

    items = items.order_by('-order__created_at')
    return _build_order_report_rows(items, include_vendor=False)


def get_all_vendors_order_report(date_from=None, date_to=None, search=None):
    """
    Full order-level report ACROSS ALL VENDORS — for superadmin.
    Search covers order number, customer details, AND vendor name/email.
    """
    items = OrderItem.objects.all().select_related(
        'order', 'product_stock', 'product', 'vendor'
    )

    if date_from:
        items = items.filter(order__created_at__date__gte=date_from)
    if date_to:
        items = items.filter(order__created_at__date__lte=date_to)

    if search:
        items = items.filter(
            models.Q(order__order_number__icontains=search) |
            models.Q(order__billing_name__icontains=search) |
            models.Q(order__billing_phone__icontains=search) |
            models.Q(order__billing_email__icontains=search) |
            models.Q(vendor__business_name__icontains=search) |
            models.Q(vendor__email__icontains=search) |
            models.Q(vendor__owner_name__icontains=search)
        )

    items = items.order_by('-order__created_at')
    return _build_order_report_rows(items, include_vendor=True)


def _build_order_report_rows(items, include_vendor=False):
    """
    Shared aggregation logic: groups OrderItem queryset by order,
    sums amounts, computes platform charge + order age.
    NOTE: when include_vendor=True, orders are split PER VENDOR
    (an order with items from 2 vendors becomes 2 rows), since each
    vendor has its own platform charge / receivable on that order.
    """
    orders_map = {}
    now = timezone.now()

    for item in items:
        order = item.order
        # key by (order_id, vendor_id) when multi-vendor, else just order_id
        key = (order.id, item.vendor_id) if include_vendor else order.id

        if key not in orders_map:
            row = {
                'order_id': order.id,
                'order_number': order.order_number,
                'order_time': order.created_at,
                'order_status': order.order_status,
                'customer_name': order.billing_name,
                'customer_phone': order.billing_phone,
                'customer_city': order.billing_city,
                'customer_email': order.billing_email,
                'payment_mode': order.payment_method,
                'order_amount': Decimal('0.00'),
                'platform_charge': Decimal('0.00'),
            }
            if include_vendor:
                row['vendor_id'] = item.vendor_id
                row['vendor_name'] = item.vendor.business_name
                row['vendor_email'] = item.vendor.email
            orders_map[key] = row

        charge = get_item_platform_charge(item)
        orders_map[key]['order_amount'] += item.total_price
        orders_map[key]['platform_charge'] += charge

    result = []
    for data in orders_map.values():
        data['received_amount'] = data['order_amount'] - data['platform_charge']
        age_delta = now - data['order_time']
        data['order_age_days'] = age_delta.days
        result.append(data)

    result.sort(key=lambda r: r['order_time'], reverse=True)
    return result