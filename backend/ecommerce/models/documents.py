from django.db import models


class SiteDocument(models.Model):
    contact_us_pdf = models.FileField(
        upload_to="documents/",
        blank=True,
        null=True,
        help_text="Upload Contact Us PDF"
    )
    privacy_policy_pdf = models.FileField(
        upload_to="documents/",
        blank=True,
        null=True,
        help_text="Upload Privacy Policy PDF"
    )
    terms_conditions_pdf = models.FileField(
        upload_to="documents/",
        blank=True,
        null=True,
        help_text="Upload Terms & Conditions PDF"
    )
    return_cancellation_pdf = models.FileField(
        upload_to="documents/",
        blank=True,
        null=True,
        help_text="Upload Refund & Cancellation PDF"
    )
    refund_pdf = models.FileField(
        upload_to="documents/",
        blank=True,
        null=True,
        help_text="Upload Return PDF"
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Site Documents"