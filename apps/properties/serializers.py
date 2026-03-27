from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import Property, PropertyImage


class PropertyImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyImage
        fields = ["id", "url", "external_url", "sort_order", "is_primary", "created_at"]

    def get_url(self, obj):
        # Return absolute URL for ImageField if present
        if obj.external_url:
            return obj.external_url
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class PropertyListSerializer(serializers.ModelSerializer):
    developer = serializers.IntegerField(source="owner_id", read_only=True)
    images = PropertyImageSerializer(many=True, read_only=True)
    moderation_status = serializers.CharField(read_only=True)
    moderation_rejection_reason = serializers.CharField(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Property
        fields = [
            "id",
            "developer",
            "type",
            "address",
            "area",
            "property_class",
            "price",
            "deadline",
            "status",
            "images",
            "created_at",
            "updated_at",
            "moderation_status",
            "moderation_rejection_reason",
        ]


class PropertyCreateSerializer(serializers.ModelSerializer):
    # owner will be set from request.user in the view
    class Meta:
        model = Property
        fields = [
            "id",
            "type",
            "address",
            "area",
            "property_class",
            "price",
            "deadline",
            "status",
        ]
        read_only_fields = ["id"]


class PropertyUpdateSerializer(serializers.ModelSerializer):
    RESET_MODERATION_FIELDS = {
        "type",
        "address",
        "area",
        "property_class",
        "price",
        "deadline",
        "status",
    }

    class Meta:
        model = Property
        fields = [
            "type",
            "address",
            "area",
            "property_class",
            "price",
            "deadline",
            "status",
        ]

    def update(self, instance, validated_data):
        has_changes = any(
            field in validated_data
            and getattr(instance, field) != validated_data[field]
            for field in self.RESET_MODERATION_FIELDS
        )

        instance = super().update(instance, validated_data)

        if has_changes:
            fields_to_update = []

            if instance.moderation_status != Property.ModerationStatuses.PENDING:
                instance.moderation_status = Property.ModerationStatuses.PENDING
                fields_to_update.append("moderation_status")

            if instance.moderation_rejection_reason is not None:
                instance.moderation_rejection_reason = None
                fields_to_update.append("moderation_rejection_reason")

            if fields_to_update:
                fields_to_update.append("updated_at")
                instance.save(update_fields=fields_to_update)

        return instance


class PropertyImageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ["image", "external_url", "sort_order", "is_primary"]

    def validate(self, attrs):
        # Require at least one source: image or external_url
        if not attrs.get("image") and not attrs.get("external_url"):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        _("Требуется либо изображение, либо внешний URL.")
                    ]
                }
            )
        return attrs


class PropertyImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ["is_primary", "sort_order"]

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError(
                {"error": _("Хотя бы одно поле должно быть передано.")}
            )
        return attrs


class MyAvailablePropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["id", "address", "area"]
