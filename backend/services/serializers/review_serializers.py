from rest_framework import serializers
from services.models.review import ServiceReview
from users.models import User
from ecommerce.models.customer import CustomerProfile
from mlm.models.agent import Agent
from pos.models.branch import Branch


class ServiceReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ServiceReview
        fields = "__all__"
        # ✅ order_item added here — it must NEVER be set directly by the
        # client. The view resolves and validates it from order_item_id.
        read_only_fields = ["user", "content_type", "object_id", "order_item"]

    def get_user_name(self, obj):
        """Get user's display name from multiple possible sources"""
        if not obj.user:
            return "Anonymous"

        user = obj.user

        # 🔥 TRY 1: Agent (Priority - kyunki agents ka business name hota hai)
        try:
            agent = Agent.objects.get(user=user)
            if agent.full_name and agent.full_name.strip():
                return agent.full_name
        except Agent.DoesNotExist:
            pass

        # 🔥 TRY 2: CustomerProfile
        try:
            profile = CustomerProfile.objects.get(user=user)
            if profile.full_name and profile.full_name.strip():
                # Agar profile ka full_name phone number hai toh skip karo
                if not profile.full_name.isdigit():
                    return profile.full_name
        except CustomerProfile.DoesNotExist:
            pass

        # 🔥 TRY 3: Branch
        try:
            branch = Branch.objects.get(user=user)
            if branch.owner_name and branch.owner_name.strip():
                return branch.owner_name
        except Branch.DoesNotExist:
            pass

        # 🔥 TRY 4: User model se first_name + last_name
        if user.first_name or user.last_name:
            full_name = f"{user.first_name} {user.last_name}".strip()
            if full_name:
                return full_name

        # 🔥 FINAL FALLBACK: Agar username phone number hai toh "User" show karo
        if user.username and user.username.isdigit():
            return "User"

        return user.username or "User"