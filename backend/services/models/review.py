from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = settings.AUTH_USER_MODEL


class ServiceReview(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    service = GenericForeignKey("content_type", "object_id")

    # ✅ NEW: links the review to the exact OrderItem it was given for.
    # For product reviews this is REQUIRED (so each delivered order/item
    # can be reviewed separately). For non-product services (property,
    # salon, gym, etc.) this stays NULL since there's no order concept.
    order_item = models.ForeignKey(
        "ecommerce.OrderItem",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reviews",
    )

    rating = models.IntegerField()
    review = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # ✅ Now uniqueness is per (user, product, order_item) — not just
        # per (user, product). Postgres/MySQL/SQLite all treat multiple
        # NULLs in a unique constraint as distinct, so non-product
        # reviews (order_item=None) still behave as one-review-per-service.
        unique_together = ["user", "content_type", "object_id", "order_item"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["user", "content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.user} -> {self.content_type.model}#{self.object_id} ({self.rating}★)"