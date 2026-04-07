from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "category",
        "event_type",
        "is_read",
        "created_at",
    )
    list_filter = ("category", "event_type", "is_read", "created_at")
    search_fields = ("user__email", "message", "title", "dedupe_key")
    raw_id_fields = ("user", "auction", "deal", "payment", "real_property")
    readonly_fields = ("created_at", "read_at")
