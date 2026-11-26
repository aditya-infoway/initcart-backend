# ecommerce/models/qrcards.py
import qrcode
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_image_size(file):
    if file.size > MAX_IMAGE_SIZE:
        raise ValidationError("Image size must be 5 MB or less.")


class QRCard(models.Model):
    """
    Digital business-card QR:
    - name/logo/links superadmin panel se manage honge
    - QR image ek dafa generate hoke fix ho jata hai (slug pe based)
      taaki print/share kiya hua QR kabhi dead na ho, chahe baad me
      naam/links edit ho jaye.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=110, unique=True, blank=True)

    logo = models.ImageField(upload_to="qrcards/logos/", blank=True, null=True)
    cover_image = models.ImageField(
        upload_to="qrcards/covers/",
        blank=True,
        null=True,
        validators=[validate_image_size],
    )
    qr_image = models.ImageField(upload_to="qrcards/qrcodes/", blank=True, null=True)

    map_link = models.URLField(blank=True, null=True)
    whatsapp_link = models.URLField(blank=True, null=True)
    google_review_link = models.URLField(blank=True, null=True)
    instagram_link = models.URLField(blank=True, null=True)
    facebook_link = models.URLField(blank=True, null=True)
    youtube_link = models.URLField(blank=True, null=True)
    website_link = models.URLField(blank=True, null=True)

    # About Us tab (rich text HTML)
    about_us = models.TextField(blank=True, null=True)

    # Contact Us tab (phone must be exactly 10 digits)
    contact_name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        validators=[RegexValidator(r"^\d{10}$", "Phone number must be exactly 10 digits.")],
    )
    email = models.EmailField(blank=True, null=True)

    # Bottom section: one link + one button text
    bottom_link = models.URLField(blank=True, null=True)
    button_text = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    # ── slug + QR generation ────────────────────────────────────────────
    def _generate_unique_slug(self):
        base_slug = slugify(self.name) or "card"
        slug = base_slug
        counter = 1
        while QRCard.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    def _generate_qr_image(self):
        # Phase-2 me nginx/domain final hone ke baad settings.QR_CARD_BASE_URL
        # update kar dena — QR isi base URL + slug ko encode karta hai.
        base_url = getattr(settings, "QR_CARD_BASE_URL", "https://initcart.com")
        public_url = f"{base_url.rstrip('/')}/{self.slug}"

        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(public_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        filename = f"{self.slug}_qr.png"
        self.qr_image.save(filename, File(buffer), save=False)

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if not self.slug:
            self.slug = self._generate_unique_slug()

        super().save(*args, **kwargs)

        # QR sirf pehli baar generate hoga (slug fix hone ke baad)
        if is_new and not self.qr_image:
            self._generate_qr_image()
            # recursive save() se bachne ke liye direct queryset update
            QRCard.objects.filter(pk=self.pk).update(qr_image=self.qr_image)


class QRCardGalleryImage(models.Model):
    """Gallery tab images (max 10 per card, 5 MB each — enforced in serializer)."""

    card = models.ForeignKey(QRCard, related_name="gallery", on_delete=models.CASCADE)
    image = models.ImageField(
        upload_to="qrcards/gallery/", validators=[validate_image_size]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.card.name} - {self.id}"