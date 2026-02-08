from __future__ import annotations

from django.contrib import admin
from django.db import transaction
from django.db.models import Max
from django.utils.html import format_html

from .models import Property, PropertyImage


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    fields = (
        "preview",
        "image",
        "external_url",
        "sort_order",
        "is_primary",
        "created_at",
    )
    readonly_fields = ("preview", "created_at")
    ordering = ("sort_order", "id")
    show_change_link = True

    def preview(self, obj: PropertyImage) -> str:
        """
        Render a small thumbnail preview for either uploaded image or external_url.
        """
        if not obj:
            return "-"

        url = None
        if obj.image and getattr(obj.image, "url", None):
            url = obj.image.url
        elif obj.external_url:
            url = obj.external_url

        if not url:
            return "-"

        return format_html(
            '<img src="{}" style="height:48px;width:auto;border-radius:6px;" />', url
        )

    preview.short_description = "preview"

    def _set_default_sort_order_if_needed(self, obj: PropertyImage) -> None:
        """
        If sort_order is left as default (0), auto-append it to the end for this property.
        """
        if obj.sort_order and obj.sort_order != 0:
            return

        max_sort = (
            PropertyImage.objects.filter(property_id=obj.property_id)
            .aggregate(m=Max("sort_order"))
            .get("m")
        )
        obj.sort_order = (max_sort or 0) + 1

    def save_model(self, request, obj, form, change):
        # Ensure deterministic ordering if sort_order wasn't explicitly set
        self._set_default_sort_order_if_needed(obj)
        super().save_model(request, obj, form, change)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "address",
        "type",
        "property_class",
        "price",
        "currency",
        "status",
        "owner",
        "created_at",
    )
    list_filter = (
        "type",
        "property_class",
        "status",
        "currency",
        ("created_at", admin.DateFieldListFilter),
        ("deadline", admin.DateFieldListFilter),
    )
    search_fields = ("address", "owner__email", "owner__username")
    autocomplete_fields = ("owner",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("owner", "type", "property_class", "status")}),
        ("Details", {"fields": ("address", "area", "price", "currency", "deadline")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    # Manage PropertyImage objects directly on the Property page
    inlines = [PropertyImageInline]

    def get_queryset(self, request):
        # Avoid N+1 for owner column in list_display
        qs = super().get_queryset(request)
        return qs.select_related("owner")


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "property_id",
        "property",
        "is_primary",
        "sort_order",
        "preview",
        "created_at",
    )
    list_filter = ("is_primary", ("created_at", admin.DateFieldListFilter))
    search_fields = ("property__address", "property__owner__email")
    autocomplete_fields = ("property",)
    ordering = ("property_id", "sort_order", "id")
    readonly_fields = ("preview", "created_at")

    fields = (
        "property",
        "image",
        "external_url",
        "sort_order",
        "is_primary",
        "preview",
        "created_at",
    )

    actions = ["make_primary"]

    def preview(self, obj: PropertyImage) -> str:
        """
        Render a larger thumbnail preview on the change form and list view.
        """
        url = None
        if obj.image and getattr(obj.image, "url", None):
            url = obj.image.url
        elif obj.external_url:
            url = obj.external_url

        if not url:
            return "-"

        return format_html(
            '<img src="{}" style="height:64px;width:auto;border-radius:8px;" />', url
        )

    preview.short_description = "preview"

    @admin.action(description="Make selected image primary (per property)")
    def make_primary(self, request, queryset):
        """
        For each property represented in the selection:
          - unset is_primary for any other image of that property
          - set is_primary=True for one chosen image (the first by id)
        This respects the DB constraint "only one primary image per property".
        """
        by_property: dict[int, list[PropertyImage]] = {}
        for img in queryset:
            by_property.setdefault(img.property_id, []).append(img)

        with transaction.atomic():
            for prop_id, images in by_property.items():
                # Pick a deterministic primary image from the selection
                primary_img = sorted(images, key=lambda x: x.id)[0]

                # Unset other primary images for this property
                PropertyImage.objects.filter(
                    property_id=prop_id, is_primary=True
                ).exclude(id=primary_img.id).update(is_primary=False)

                # Set the chosen one as primary
                PropertyImage.objects.filter(id=primary_img.id).update(is_primary=True)
