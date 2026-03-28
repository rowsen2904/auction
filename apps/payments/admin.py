from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "deal", "type", "amount", "rate", "status", "created_at")
    list_filter = ("type", "status")
    raw_id_fields = ("deal",)
