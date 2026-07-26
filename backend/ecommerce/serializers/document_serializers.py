from rest_framework import serializers
from ecommerce.models.documents import SiteDocument


class SiteDocumentSerializer(serializers.ModelSerializer):
    contact_us_pdf_url = serializers.SerializerMethodField()
    privacy_policy_pdf_url = serializers.SerializerMethodField()
    terms_conditions_pdf_url = serializers.SerializerMethodField()
    return_cancellation_pdf_url = serializers.SerializerMethodField()
    refund_pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = SiteDocument
        fields = [
            "contact_us_pdf", "contact_us_pdf_url",
            "privacy_policy_pdf", "privacy_policy_pdf_url",
            "terms_conditions_pdf", "terms_conditions_pdf_url",
            "return_cancellation_pdf", "return_cancellation_pdf_url",
            "refund_pdf", "refund_pdf_url",
            "updated_at",
        ]
        extra_kwargs = {
            "contact_us_pdf": {"required": False},
            "privacy_policy_pdf": {"required": False},
            "terms_conditions_pdf": {"required": False},
            "return_cancellation_pdf": {"required": False},
            "refund_pdf": {"required": False},
        }

    def _build_url(self, obj, field_name):
        file_field = getattr(obj, field_name)
        if file_field:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(file_field.url)
            return file_field.url
        return ""

    def get_contact_us_pdf_url(self, obj):
        return self._build_url(obj, "contact_us_pdf")

    def get_privacy_policy_pdf_url(self, obj):
        return self._build_url(obj, "privacy_policy_pdf")

    def get_terms_conditions_pdf_url(self, obj):
        return self._build_url(obj, "terms_conditions_pdf")

    def get_return_cancellation_pdf_url(self, obj):
        return self._build_url(obj, "return_cancellation_pdf")
    
    def get_refund_pdf_url(self, obj):
        return self._build_url(obj, "refund_pdf")


class PublicSiteDocumentSerializer(serializers.ModelSerializer):
    """Read-only serializer for the public website footer/pages."""

    contact_us_pdf_url = serializers.SerializerMethodField()
    privacy_policy_pdf_url = serializers.SerializerMethodField()
    terms_conditions_pdf_url = serializers.SerializerMethodField()
    return_cancellation_pdf_url = serializers.SerializerMethodField()
    refund_pdf_url = serializers.SerializerMethodField()
    class Meta:
        model = SiteDocument
        fields = [
            "contact_us_pdf_url",
            "privacy_policy_pdf_url",
            "terms_conditions_pdf_url",
            "return_cancellation_pdf_url",
            "refund_pdf_url",
        ]

    def _build_url(self, obj, field_name):
        file_field = getattr(obj, field_name)
        if file_field:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(file_field.url)
            return file_field.url
        return ""

    def get_contact_us_pdf_url(self, obj):
        return self._build_url(obj, "contact_us_pdf")

    def get_privacy_policy_pdf_url(self, obj):
        return self._build_url(obj, "privacy_policy_pdf")

    def get_terms_conditions_pdf_url(self, obj):
        return self._build_url(obj, "terms_conditions_pdf")

    def get_return_cancellation_pdf_url(self, obj):
        return self._build_url(obj, "return_cancellation_pdf")
    
    def get_refund_pdf_url(self, obj):
        return self._build_url(obj, "refund_pdf")