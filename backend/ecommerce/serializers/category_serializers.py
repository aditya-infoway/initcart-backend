from rest_framework import serializers
from ecommerce.models.category import Category, SubCategory, SubSubCategory, CategorySectionSetting, SubCategorySectionSetting

class CategorySectionSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CategorySectionSetting
        fields = ["eyebrow", "heading"]

class SubCategorySectionSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategorySectionSetting
        fields = ["overlay_color"]

class CategorySerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "description", "icon", "icon_url",
                  "banner_image", "banner_url",
                  "status", "is_featured", "featured_order",
                  "web_home", "platform_charge"]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.icon.url) if obj.icon and request else None

    def get_banner_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.banner_image.url) if obj.banner_image and request else None

class SubCategorySerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = SubCategory
        fields = ["id", "category", "category_name", "name", "description",
                  "icon", "icon_url", "banner_image", "banner_url", "status",]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.icon.url) if obj.icon and request else None

    def get_banner_url(self, obj):
        request = self.context.get("request")
        return request.build_absolute_uri(obj.banner_image.url) if obj.banner_image and request else None


class SubSubCategorySerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()
    category_id = serializers.IntegerField(source="subcategory.category.id", read_only=True)
    subcategory_name = serializers.CharField(source="subcategory.name", read_only=True)

    class Meta:
        model = SubSubCategory
        fields = ["id", "subcategory", "subcategory_name", "category_id",
                  "name", "icon", "icon_url", "status"]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        if obj.icon and request:
            return request.build_absolute_uri(obj.icon.url)
        return None
