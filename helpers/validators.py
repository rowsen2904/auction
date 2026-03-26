from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class FileSizeValidationMixin:
    MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB

    def _validate_file_size(self, file, field_name: str):
        if not file:
            return file
        if file.size > self.MAX_FILE_SIZE:
            raise serializers.ValidationError(
                _("File is too large (max 5MB)."),
                code="file_too_large",
            )
        return file
