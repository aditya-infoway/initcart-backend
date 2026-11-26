# qrcards/serializers.py
import re

from django.db import transaction
from rest_framework import serializers

from ecommerce.models.qrcards import (
    QRCard,
    QRCardGalleryImage,
    validate_image_size,
)

MAX_GALLERY_IMAGES = 10


class QRCardGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = QRCardGalleryImage
        fields = ["id", "image"]


class QRCardSerializer(serializers.ModelSerializer):
    # Read: list of gallery images
    gallery = QRCardGallerySerializer(many=True, read_only=True)

    # Write: new gallery files + ids of existing images to delete (edit)
    gallery_images = serializers.ListField(
        child=serializers.ImageField(validators=[validate_image_size]),
        write_only=True,
        required=False,
    )
    remove_gallery_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )


    class Meta:
        model = QRCard
        fields = [
            "id",
            "name",
            "slug",
            "logo",
            "cover_image",
            "qr_image",
            "map_link",
            "whatsapp_link",
            "google_review_link",
            "instagram_link",
            "facebook_link",
            "youtube_link",
            "website_link",
            "about_us",
            "gallery",
            "gallery_images",
            "remove_gallery_ids",
            "contact_name",
            "phone",
            "email",
            "bottom_link",
            "button_text",
            "created_at",
            "updated_at",
            
        ]
        # slug aur qr_image system-generated hai — user edit nahi karega
        read_only_fields = ["slug", "qr_image", "created_at", "updated_at"]

    def validate_phone(self, value):
        if not value:
            return value
        if not re.fullmatch(r"\d{10}", value.strip()):
            raise serializers.ValidationError("Phone number must be exactly 10 digits.")
        return value.strip()

    def validate(self, attrs):
        new_images = attrs.get("gallery_images", [])
        remove_ids = attrs.get("remove_gallery_ids", [])

        existing = 0
        if self.instance:
            existing = self.instance.gallery.exclude(id__in=remove_ids).count()

        if existing + len(new_images) > MAX_GALLERY_IMAGES:
            raise serializers.ValidationError(
                {"gallery_images": f"Maximum {MAX_GALLERY_IMAGES} gallery images allowed."}
            )
        return attrs

    def _add_gallery(self, card, images):
        for image in images:
            QRCardGalleryImage.objects.create(card=card, image=image)

    @transaction.atomic
    def create(self, validated_data):
        images = validated_data.pop("gallery_images", [])
        validated_data.pop("remove_gallery_ids", None)
        card = super().create(validated_data)
        self._add_gallery(card, images)
        return card

    @transaction.atomic
    def update(self, instance, validated_data):
        images = validated_data.pop("gallery_images", [])
        remove_ids = validated_data.pop("remove_gallery_ids", [])
        card = super().update(instance, validated_data)
        if remove_ids:
            card.gallery.filter(id__in=remove_ids).delete()
        self._add_gallery(card, images)
        return card