# qrcards/serializers.py
from rest_framework import serializers
from ecommerce.models.qrcards import QRCard


class QRCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = QRCard
        fields = [
            "id",
            "name",
            "slug",
            "logo",
            "qr_image",
            "map_link",
            "whatsapp_link",
            "google_review_link",
            "instagram_link",
            "facebook_link",
            "youtube_link",
            "website_link",
            "created_at",
            "updated_at",
        ]
        # slug aur qr_image system-generated hai — user edit nahi karega
        read_only_fields = ["slug", "qr_image", "created_at", "updated_at"]