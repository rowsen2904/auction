from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.users.serializers import BrokerInfoSerializer, DeveloperInfoSerializer

User = get_user_model()


class BrokerVerificationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    action = serializers.ChoiceField(choices=("accept", "reject"))


class UserSerializer(serializers.ModelSerializer):
    broker = BrokerInfoSerializer(read_only=True)
    developer = DeveloperInfoSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "broker",
            "developer",
        ]
