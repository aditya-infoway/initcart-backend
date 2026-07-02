from rest_framework import serializers
from ecommerce.models.category import Category, SubCategory, SubSubCategory


class CategorySerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id", "name", "description", "icon", "icon_url", 
            "status", "is_featured", "featured_order",
            "web_home", "platform_charge"  
        ]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        if obj.icon and request:
            return request.build_absolute_uri(obj.icon.url)
        return None

class SubCategorySerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = SubCategory
        fields = ["id", "category", "category_name", "name", "icon", "icon_url", "status"]

    def get_icon_url(self, obj):
        request = self.context.get("request")
        if obj.icon and request:
            return request.build_absolute_uri(obj.icon.url)
        return None


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
