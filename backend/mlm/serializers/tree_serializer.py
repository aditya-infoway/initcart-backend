#mlm/serializers/tree_serializer.py
from rest_framework import serializers
from mlm.models.agent import Agent
from users.models import User


class DownlineTreeSerializer(serializers.ModelSerializer):

    downlines = serializers.SerializerMethodField()
    user_id = serializers.IntegerField(source="user.id")

    class Meta:
        model = Agent
        fields = [
            "id",
            "user_id",
            "full_name",
            "agent_type",
            "city",
            "state",
            "downlines"
        ]

    def get_downlines(self, obj):

        children_users = User.objects.filter(referred_by=obj.user)

        agents = Agent.objects.filter(user__in=children_users, status="approved")

        return DownlineTreeSerializer(agents, many=True).data