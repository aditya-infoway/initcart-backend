# pos/serializers/employee_serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from pos.models.employee import Employee, EmployeePermission

User = get_user_model()


class EmployeePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmployeePermission
        fields = ['id', 'page_key', 'page_label', 'can_view', 'can_add', 'can_edit', 'can_delete']


class EmployeeCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = Employee
        fields = ['id', 'full_name', 'mobile', 'email', 'password', 'city', 'address', 'department', 'status']

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ye email pehle se register hai.")
        if Employee.objects.filter(email=value).exists():
            raise serializers.ValidationError("this email already exist.")
        return value

    def validate_mobile(self, value):
        if not value.isdigit() or len(value) != 10:
            raise serializers.ValidationError("Mobile number should be 10 digit.")
        return value

    def create(self, validated_data):
        request = self.context['request']
        branch = getattr(request.user, 'branch', None)
        if branch is None:
            raise serializers.ValidationError("only superadmin who linked with branch can create employee.")

        password = validated_data.pop('password')
        email = validated_data['email']
        full_name = validated_data.get('full_name', '').strip()

        name_parts = full_name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        user = User.objects.create(
            username=email,
            email=email,
            role='employee',
            phone=validated_data.get('mobile', ''),
            first_name=first_name,   # ✅ add kiya
            last_name=last_name,     # ✅ add kiya
        )
        user.set_password(password)
        user.save()

        employee = Employee.objects.create(user=user, branch=branch, **validated_data)
        return employee


class EmployeeListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)   # ✅ add

    class Meta:
        model = Employee
        fields = ['id', 'full_name', 'mobile', 'email', 'city', 'address',
                  'department', 'status', 'branch_name', 'username', 'created_at']


class EmployeeDetailSerializer(serializers.ModelSerializer):
    permissions = EmployeePermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Employee
        fields = ['id', 'full_name', 'mobile', 'email', 'city', 'address',
                  'department', 'status', 'permissions']


class EmployeeUpdateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=6)

    class Meta:
        model = Employee
        fields = ['full_name', 'mobile', 'city', 'address', 'department', 'status', 'password']

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # ✅ full_name change hua to user ka first/last name bhi update karo
        if 'full_name' in validated_data:
            name_parts = validated_data['full_name'].strip().split()
            instance.user.first_name = name_parts[0] if name_parts else ""
            instance.user.last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            instance.user.save(update_fields=["first_name", "last_name"])

        if password:
            instance.user.set_password(password)
            instance.user.save()
        return instance 