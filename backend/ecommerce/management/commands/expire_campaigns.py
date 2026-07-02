from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connection

class Command(BaseCommand):
    help = 'Expire old campaigns (simple version)'
    
    def handle(self, *args, **options):
        now = timezone.now()
        
        # Direct SQL query - Product model की जरूरत नहीं
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE ecommerce_campaign 
                SET status = 'Expired' 
                WHERE end_datetime < %s AND status = 'Active'
            """, [now])
            
            count = cursor.rowcount
        
        self.stdout.write(f"{count} campaigns expired")