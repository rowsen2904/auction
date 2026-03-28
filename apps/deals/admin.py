from django.contrib import admin

from .models import Deal, DealLog


class DealLogInline(admin.TabularInline):
    model = DealLog
    extra = 0
    readonly_fields = ("action", "actor", "detail", "created_at")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("id", "auction", "broker", "developer", "status", "obligation_status", "created_at")
    list_filter = ("status", "obligation_status")
    search_fields = ("broker__email", "developer__email", "real_property__address")
    raw_id_fields = ("auction", "bid", "broker", "developer", "real_property")
    inlines = [DealLogInline]


@admin.register(DealLog)
class DealLogAdmin(admin.ModelAdmin):
    list_display = ("id", "deal", "action", "actor", "created_at")
    list_filter = ("action",)
    raw_id_fields = ("deal", "actor")
