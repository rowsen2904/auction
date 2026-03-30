from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from properties.models import Property
from rest_framework import serializers

from .models import Auction, Bid
from .tasks import schedule_auction_status_tasks

User = get_user_model()


class AuctionPropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["id", "address"]


class BidBrokerShortSerializer(serializers.ModelSerializer):
    fullname = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "fullname"]
        read_only_fields = fields


class WinnerBidShortSerializer(serializers.ModelSerializer):
    broker = BidBrokerShortSerializer(read_only=True)

    class Meta:
        model = Bid
        fields = ["id", "broker", "amount", "is_sealed"]
        read_only_fields = fields


class BidSerializer(serializers.ModelSerializer):
    broker_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Bid
        fields = ["id", "auction_id", "broker_id", "amount", "created_at"]
        read_only_fields = ["id", "auction_id", "broker_id", "created_at"]


class AuctionListSerializer(serializers.ModelSerializer):
    # Model has real_property, but API expects property_id
    real_property = AuctionPropertySerializer(read_only=True)
    owner_id = serializers.IntegerField(read_only=True)
    highest_bid_id = serializers.IntegerField(read_only=True)
    winner_bid = WinnerBidShortSerializer(read_only=True)

    class Meta:
        model = Auction
        fields = [
            "id",
            "real_property",
            "owner_id",
            "mode",
            "min_price",
            "min_bid_increment",
            "start_date",
            "end_date",
            "status",
            "bids_count",
            "current_price",
            "highest_bid_id",
            "winner_bid",
            "created_at",
            "updated_at",
        ]


class AuctionCreateSerializer(serializers.ModelSerializer):
    property_id = serializers.PrimaryKeyRelatedField(
        source="real_property",
        queryset=Property.objects.all(),
        write_only=True,
    )
    min_bid_increment = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Auction
        fields = [
            "property_id",
            "mode",
            "min_price",
            "min_bid_increment",
            "start_date",
            "end_date",
        ]

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        mode = attrs.get("mode")
        min_bid_increment = attrs.get("min_bid_increment")
        now = timezone.now()

        min_offset = getattr(settings, "AUCTION_MIN_START_OFFSET", timedelta(seconds=1))
        min_dur = getattr(settings, "AUCTION_MIN_DURATION", timedelta(hours=1))
        max_dur = getattr(settings, "AUCTION_MAX_DURATION", timedelta(days=30))

        prop = attrs.get("real_property") or getattr(
            self.instance, "real_property", None
        )

        if prop is None:
            raise serializers.ValidationError(
                {"real_property": "Это поле обязательно для заполнения."}
            )

        if prop.moderation_status != Property.ModerationStatuses.APPROVED:
            raise serializers.ValidationError(
                {
                    "real_property": "Объект недвижимости должен быть одобрен администрацией."
                }
            )

        if Auction.objects.filter(real_property_id=prop.id).exists():
            raise serializers.ValidationError(
                {"real_property": "Для этого объекта недвижимости аукцион уже создан."}
            )

        if start and start < now + min_offset:
            raise serializers.ValidationError(
                {
                    "start_date": f"Дата начала должна быть не менее чем на {min_offset} "
                    "от текущего момента."
                }
            )

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_date": "Дата окончания должна быть больше даты начала."}
            )

        if start and end:
            dur = end - start
            if dur < min_dur:
                raise serializers.ValidationError(
                    {"end_date": f"Продолжительность должна быть не менее {min_dur}."}
                )
            if dur > max_dur:
                raise serializers.ValidationError(
                    {"end_date": f"Продолжительность должна быть не более {max_dur}."}
                )

        if mode == Auction.Mode.OPEN:
            if min_bid_increment is None:
                raise serializers.ValidationError(
                    {
                        "min_bid_increment": (
                            "Для открытого аукциона необходимо указать минимальный шаг ставки."
                        )
                    }
                )

            if min_bid_increment < Decimal("1.00"):
                raise serializers.ValidationError(
                    {
                        "min_bid_increment": (
                            "Минимальный шаг ставки должен быть не меньше 1."
                        )
                    }
                )

        elif mode == Auction.Mode.CLOSED:
            attrs["min_bid_increment"] = None

        return attrs

    def validate_property_id(self, prop: Property):
        request = self.context["request"]
        if prop.owner_id != request.user.id:
            raise serializers.ValidationError(
                "Вы можете создавать аукционы только для своей собственной недвижимости."
            )
        return prop

    def create(self, validated_data):
        request = self.context["request"]
        auction = Auction.objects.create(
            owner=request.user,
            status=Auction.Status.SCHEDULED,
            **validated_data,
        )

        transaction.on_commit(
            lambda: schedule_auction_status_tasks(
                auction_id=auction.id,
                start_date=auction.start_date,
                end_date=auction.end_date,
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


class BidUpdateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class ParticipantsListSerializer(serializers.Serializer):
    auction_id = serializers.IntegerField()
    participants = serializers.ListField(child=serializers.IntegerField())


class ClosedShortlistSerializer(serializers.Serializer):
    bid_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class ClosedSelectWinnerSerializer(serializers.Serializer):
    bid_id = serializers.IntegerField(min_value=1)
