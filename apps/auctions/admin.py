from __future__ import annotations

from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html

from .models import Auction, Bid


class BidInline(admin.TabularInline):
    model = Bid
    extra = 0
    fields = ("id", "broker", "amount", "created_at")
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("broker",)
    ordering = ("-created_at",)
    show_change_link = True


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "real_property",
        "owner",
        "mode",
        "status",
        "min_price",
        "current_price",
        "bids_count",
        "start_date",
        "end_date",
        "highest_bid_link",
        "winner_bid_link",
        "created_at",
    )
    list_filter = (
        "mode",
        "status",
        ("created_at", admin.DateFieldListFilter),
        ("start_date", admin.DateFieldListFilter),
        ("end_date", admin.DateFieldListFilter),
    )
    search_fields = (
        "id",
        "real_property__address",
        "owner__email",
        "owner__username",
    )
    autocomplete_fields = ("real_property", "owner", "highest_bid", "winner_bid")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    readonly_fields = ("bids_count", "current_price", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("real_property", "owner", "mode", "status")}),
        ("Rules", {"fields": ("min_price", "start_date", "end_date")}),
        (
            "Cached fields",
            {"fields": ("bids_count", "current_price", "highest_bid", "winner_bid")},
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    inlines = [BidInline]

    actions = ["mark_active", "mark_cancelled", "mark_finished"]

    def get_queryset(self, request):
        # Avoid N+1 queries for list_display relations
        qs = super().get_queryset(request)
        return qs.select_related("real_property", "owner", "highest_bid", "winner_bid")

    def highest_bid_link(self, obj: Auction) -> str:
        """
        Render a quick link to the highest bid object (if any).
        """
        if not obj.highest_bid_id:
            return "-"
        return format_html(
            '<a href="/admin/auctions/bid/{}/change/">Bid #{}</a>',
            obj.highest_bid_id,
            obj.highest_bid_id,
        )

    highest_bid_link.short_description = "highest_bid"

    def winner_bid_link(self, obj: Auction) -> str:
        """
        Render a quick link to the winner bid object (if any).
        """
        if not obj.winner_bid_id:
            return "-"
        return format_html(
            '<a href="/admin/auctions/bid/{}/change/">Bid #{}</a>',
            obj.winner_bid_id,
            obj.winner_bid_id,
        )

    winner_bid_link.short_description = "winner_bid"

    @admin.action(description="Mark selected auctions as ACTIVE")
    def mark_active(self, request, queryset):
        """
        Simple bulk action to set status=ACTIVE.
        Note: does not validate dates; intended for admin override.
        """
        queryset.update(status=Auction.Status.ACTIVE)

    @admin.action(description="Mark selected auctions as CANCELLED")
    def mark_cancelled(self, request, queryset):
        """
        Simple bulk action to set status=CANCELLED.
        """
        queryset.update(status=Auction.Status.CANCELLED)

    @admin.action(description="Mark selected auctions as FINISHED")
    def mark_finished(self, request, queryset):
        """
        Simple bulk action to set status=FINISHED.
        """
        queryset.update(status=Auction.Status.FINISHED)


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ("id", "auction", "broker", "amount", "created_at")
    list_filter = (("created_at", admin.DateFieldListFilter),)
    search_fields = (
        "id",
        "auction__id",
        "auction__real_property__address",
        "broker__email",
        "broker__username",
    )
    autocomplete_fields = ("auction", "broker")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    actions = ["recompute_auction_cache_for_selected_bids"]

    def get_queryset(self, request):
        # Avoid N+1 in list_display
        qs = super().get_queryset(request)
        return qs.select_related("auction", "broker", "auction__real_property")

    @admin.action(
        description="Recompute auction cache (bids_count/current_price/highest_bid)"
        "for affected auctions"
    )
    def recompute_auction_cache_for_selected_bids(self, request, queryset):
        """
        Admin-only repair action:
        Recalculate bids_count, current_price, and highest_bid based on the Bid table.
        Useful if you imported data or changed logic and want to re-sync denormalized fields.
        """
        auction_ids = set(queryset.values_list("auction_id", flat=True))
        if not auction_ids:
            return

        with transaction.atomic():
            for auction_id in auction_ids:
                auction = Auction.objects.select_for_update().get(id=auction_id)

                bids_qs = Bid.objects.filter(auction_id=auction_id)
                bids_count = bids_qs.count()

                highest = bids_qs.order_by("-amount", "-created_at").first()
                if highest:
                    auction.current_price = highest.amount
                    auction.highest_bid_id = highest.id
                else:
                    auction.current_price = 0
                    auction.highest_bid_id = None

                auction.bids_count = bids_count
                auction.save(
                    update_fields=[
                        "bids_count",
                        "current_price",
                        "highest_bid",
                        "updated_at",
                    ]
                )
