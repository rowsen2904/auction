from __future__ import annotations

from rest_framework import serializers

from .models import DocumentRequest, DocumentRequestFile


class DocumentRequestFileSerializer(serializers.ModelSerializer):
    file = serializers.SerializerMethodField()

    class Meta:
        model = DocumentRequestFile
        fields = ["id", "file", "uploaded_at"]

    def get_file(self, obj: DocumentRequestFile) -> str | None:
        if not obj.file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if request else obj.file.url


class DocumentRequestSerializer(serializers.ModelSerializer):
    requested_by_email = serializers.CharField(
        source="requested_by.email", read_only=True
    )
    broker_email = serializers.CharField(source="broker.email", read_only=True)
    response_documents = DocumentRequestFileSerializer(many=True, read_only=True)

    class Meta:
        model = DocumentRequest
        fields = [
            "id",
            "auction",
            "broker",
            "broker_email",
            "requested_by",
            "requested_by_email",
            "description",
            "broker_comment",
            "status",
            "response_documents",
            "created_at",
            "updated_at",
            "answered_at",
        ]
        read_only_fields = fields


class CreateDocumentRequestSerializer(serializers.Serializer):
    broker_id = serializers.IntegerField(min_value=1)
    description = serializers.CharField(max_length=4000, allow_blank=False)


class UploadDocumentRequestSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        min_length=1,
        max_length=20,
    )
    broker_comment = serializers.CharField(
        required=False, allow_blank=True, max_length=2000, default=""
    )
