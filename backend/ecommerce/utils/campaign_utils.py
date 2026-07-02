# ecommerce/utils/campaign_utils.py
from django.utils import timezone
from ecommerce.models.campaign import Campaign, CampaignProduct

def get_campaign_price_for_product(product, request=None):
    """
    Returns campaign price if product is in active campaign
    Returns None if no active campaign
    """
    now = timezone.now()
    
    # Check all campaign types
    campaign_product = CampaignProduct.objects.filter(
        product=product,
        status='Approved',
        participation__campaign__status='Active',
        participation__campaign__start_datetime__lte=now,
        participation__campaign__end_datetime__gte=now
    ).select_related('participation__campaign').first()
    
    if campaign_product:
        return {
            'campaign_price': campaign_product.final_price,
            'original_price': campaign_product.original_price,
            'discount_percentage': campaign_product.discount_percentage,
            'campaign_id': campaign_product.participation.campaign.id,
            'campaign_name': campaign_product.participation.campaign.campaign_name,
            'campaign_type': campaign_product.participation.campaign.campaign_type,
            'deal_of_day_placement': campaign_product.deal_of_day_placement,
            'end_datetime': campaign_product.participation.campaign.end_datetime,
            'campaign_product_id': campaign_product.id
        }
    return None