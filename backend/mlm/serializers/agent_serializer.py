# mlm/serializers/agent_serializers.py
from rest_framework import serializers
from mlm.models.agent import Agent
from mlm.models.mlm_settings import MLMSettings
from users.models import User
from django.contrib.auth.hashers import make_password


class AgentRegistrationSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True, write_only=True)  #  write_only add karo
    created_by = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Agent
        fields = "__all__"
        read_only_fields = ["status", "user", "created_by"]

    def get_created_by(self, obj):
        """Return created_by username"""
        if obj.created_by:
            return {
                'id': obj.created_by.id,
                'username': obj.created_by.username
            }
        return None

    def validate(self, data):
        agent_type = data.get("agent_type")
        contact_number = data.get("contact_number")
        
        # Check if username (contact_number) already exists
        if User.objects.filter(username=contact_number).exists():
            raise serializers.ValidationError(
                {"contact_number": "This mobile number is already registered. Please use a different number."}
            )

        if agent_type in ["pos", "society"]:
            if not data.get("gst_certificate"):
                raise serializers.ValidationError(
                    {"gst_certificate": "GST certificate required"}
                )
            if not data.get("business_license"):
                raise serializers.ValidationError(
                    {"business_license": "Business license required"}
                )

        # Check parent agent's minimum sales
        referral_code = self.context["request"].data.get("referral_code")
        
        if referral_code:
            try:
                parent_user = User.objects.get(referral_code=referral_code)
                
                try:
                    parent_agent = Agent.objects.get(user=parent_user, status="approved")
                    
                    settings = MLMSettings.objects.first()
                    if not settings:
                        raise serializers.ValidationError(
                            {"referral_code": "MLM settings not configured. Please contact admin."}
                        )
                    #  ADD KARO: POS branch agent parent ke liye minimum sales skip
                    skip_min_check = (
                        parent_agent.agent_type == "pos"
                        and getattr(parent_agent, 'is_pos_branch_agent', False)
                    )

                    if not skip_min_check and parent_agent.total_sales < settings.minimum_sale_amount:
                        raise serializers.ValidationError(
                            {"referral_code": f"This agent has not completed the minimum sales requirement (₹{settings.minimum_sale_amount}) to refer new agents."}
                        )    
                    
                    # if parent_agent.total_sales < settings.minimum_sale_amount:
                    #     raise serializers.ValidationError(
                    #         {"referral_code": f"This agent has not completed the minimum sales requirement (₹{settings.minimum_sale_amount}) to refer new agents."}
                    #     )
                    
                    if not parent_agent.is_active_agent:
                        raise serializers.ValidationError(
                            {"referral_code": "This agent is not active to refer new agents."}
                        )
                    
                except Agent.DoesNotExist:
                    raise serializers.ValidationError(
                        {"referral_code": "Invalid referral code. The user is not an approved agent."}
                    )
                    
            except User.DoesNotExist:
                raise serializers.ValidationError(
                    {"referral_code": "Invalid referral code. Please check and try again."}
                )

        return data

    def create(self, validated_data):
        # ✅ Email ko pehle hi nikal lo
        password = validated_data.pop("password")
        email = validated_data.pop("email")  # ✅ Email ko validated_data se pop karo
        referral_code = self.context["request"].data.get("referral_code")
        request = self.context.get("request")

        sponsor = None
        if referral_code:
            try:
                sponsor = User.objects.get(referral_code=referral_code)
            except User.DoesNotExist:
                sponsor = None

        #  Create user with email
        user = User.objects.create_user(
            username=validated_data["contact_number"],
            password=password,
            email=email,  #  Email properly set karo
            role="both",
            user_type="both",
            referred_by=sponsor
        )

        #  Agent create karte time email ko dobara set karo
        agent = Agent.objects.create(
            user=user,
            email=email,  #  Explicitly set karo
            created_by=request.user if request and request.user.is_authenticated else None,
            **validated_data
        )

        return agent

class AgentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating agents"""
    
    password = serializers.CharField(write_only=True, required=False)
    
    class Meta:
        model = Agent
        fields = "__all__"
        read_only_fields = ["status", "user", "created_by", "created_at"]
    
    def validate_contact_number(self, value):
        """Check if contact number is being changed and if it's already taken"""
        if self.instance and self.instance.contact_number != value:
            if User.objects.filter(username=value).exclude(id=self.instance.user.id).exists():
                raise serializers.ValidationError("This mobile number is already registered with another agent.")
        return value
    
    def update(self, instance, validated_data):
        # Update Agent fields
        for attr, value in validated_data.items():
            if attr != 'password':
                setattr(instance, attr, value)
        
        instance.save()
        
        # Update password if provided
        if 'password' in validated_data and validated_data['password']:
            user = instance.user
            user.set_password(validated_data['password'])
            user.save()
        
        # Update username if contact_number changed
        if 'contact_number' in validated_data and instance.contact_number != instance.user.username:
            user = instance.user
            user.username = validated_data['contact_number']
            user.save()
        
        return instance