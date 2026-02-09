from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from properties.models import Property
from rest_framework import serializers

from .models import Auction, Bid
from .tasks import schedule_auction_status_tasks


class BidSerializer(serializers.ModelSerializer):
    broker_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Bid
        fields = ["id", "auction_id", "broker_id", "amount", "created_at"]
        read_only_fields = ["id", "auction_id", "broker_id", "created_at"]


class AuctionListSerializer(serializers.ModelSerializer):
    # Model has real_property, but API expects property_id
    property_id = serializers.IntegerField(source="real_property_id", read_only=True)

    owner_id = serializers.IntegerField(read_only=True)
    highest_bid_id = serializers.IntegerField(read_only=True)
    winner_bid_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Auction
        fields = [
            "id",
            "property_id",
            "owner_id",
            "mode",
            "min_price",
            "start_date",
            "end_date",
            "status",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "winner_bid_id",
            "created_at",
            "updated_at",
        ]


class AuctionCreateSerializer(serializers.ModelSerializer):
    # API accepts property_id, but model field is real_property
    property_id = serializers.PrimaryKeyRelatedField(
        source="real_property",
        queryset=Property.objects.all(),
        write_only=True,
    )

    class Meta:
        model = Auction
        fields = ["property_id", "mode", "min_price", "start_date", "end_date"]

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        now = timezone.now()

        if start and start < now + timedelta(hours=1):
            raise serializers.ValidationError(
                {"start_date": "start_date must be at least 1 hour from now."}
            )

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_date": "end_date must be greater than start_date."}
            )

        # Extra safety (optional)
        if end and end <= now:
            raise serializers.ValidationError(
                {"end_date": "end_date must be in the future."}
            )

        return attrs

    def validate_property_id(self, prop: Property):
        # Only allow creating auctions for properties owned by the developer
        request = self.context["request"]
        if prop.owner_id != request.user.id:
            raise serializers.ValidationError(
                "You can only create auctions for your own properties."
            )
        return prop

    def create(self, validated_data):
        request = self.context["request"]

        # Always create as DRAFT (it will become ACTIVE via beat at start_date)
        auction = Auction.objects.create(
            owner=request.user,
            status=Auction.Status.DRAFT,
            **validated_data,
        )

        # Create beat tasks only after DB commit (no orphan tasks on rollback)
        start_date = auction.start_date
        end_date = auction.end_date

        transaction.on_commit(
            lambda: schedule_auction_status_tasks(
                auction_id=auction.id,
                start_date=start_date,
                end_date=end_date,
            )
        )

        return auction


class AuctionDetailSerializer(AuctionListSerializer):
    bids = serializers.SerializerMethodField()
    start_date = serializers.DateTimeField()

    class Meta(AuctionListSerializer.Meta):
        fields = AuctionListSerializer.Meta.fields + ["bids"]

    def get_bids(self, obj: Auction):
        request = self.context.get("request")

        # Open auctions: bids are public
        if obj.mode == Auction.Mode.OPEN:
            qs = obj.bids.select_related("broker").order_by("-created_at")[:50]
            return BidSerializer(qs, many=True).data

        # Closed auctions: bids are visible only to owner
        if (
            request
            and request.user.is_authenticated
            and obj.owner_id == request.user.id
        ):
            qs = obj.bids.select_related("broker").order_by("-created_at")
            return BidSerializer(qs, many=True).data

        return []


class BidCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )


class SelectWinnerSerializer(serializers.Serializer):
    bid_id = serializers.IntegerField(min_value=1)
