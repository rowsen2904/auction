from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from properties.models import Property
from properties.services.compatibility import (
    BLOCKING_AUCTION_STATUSES,
    validate_lot_compatibility,
)
from rest_framework import serializers

from .models import Auction, AuctionProperty, Bid
from .tasks import schedule_auction_status_tasks

User = get_user_model()


class AuctionPropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["id", "reference_id", "address"]


class AuctionLotPropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = [
            "id",
            "reference_id",
            "type",
            "project",
            "rooms",
            "purpose",
            "address",
            "area",
            "property_class",
            "price",
            "commission_rate",
            "deadline",
            "delivery_date",
            "status",
            "moderation_status",
        ]


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
    real_property = AuctionPropertySerializer(read_only=True)
    properties = AuctionLotPropertySerializer(many=True, read_only=True)
    owner_id = serializers.IntegerField(read_only=True)
    highest_bid_id = serializers.IntegerField(read_only=True)
    winner_bid = WinnerBidShortSerializer(read_only=True)
    lot_total_price = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    deals_created = serializers.SerializerMethodField()

    class Meta:
        model = Auction
        fields = [
            "id",
            "real_property",
            "properties",
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
            "lot_total_price",
            "deals_created",
            "created_at",
            "updated_at",
        ]

    def get_deals_created(self, obj):
        from deals.models import Deal

        return Deal.objects.filter(auction_id=obj.id).exists()

    def _is_broker_request(self) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(
            user and user.is_authenticated and getattr(user, "is_broker", False)
        )

    def _hide_closed_summary_for_broker(self, obj: Auction, data: dict) -> None:
        if obj.mode != Auction.Mode.CLOSED:
            return
        if not self._is_broker_request():
            return

        data["min_price"] = None
        data["current_price"] = None
        data["bids_count"] = None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        self._hide_closed_summary_for_broker(instance, data)
        return data


class AuctionCreateSerializer(serializers.ModelSerializer):
    # new contract
    propertyId = serializers.IntegerField(required=False, write_only=True, min_value=1)
    propertyIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
        allow_empty=False,
    )

    # backward compatibility
    property_id = serializers.IntegerField(required=False, write_only=True, min_value=1)
    property_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        write_only=True,
        allow_empty=False,
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
            "propertyId",
            "propertyIds",
            "property_id",
            "property_ids",
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

        min_offset = getattr(settings, "AUCTION_MIN_START_OFFSET", timedelta(hours=1))
        min_dur = getattr(settings, "AUCTION_MIN_DURATION", timedelta(hours=12))
        max_dur = getattr(settings, "AUCTION_MAX_DURATION", timedelta(days=30))

        camel_single = attrs.pop("propertyId", None)
        camel_many = attrs.pop("propertyIds", None)
        snake_single = attrs.pop("property_id", None)
        snake_many = attrs.pop("property_ids", None)

        if camel_single is not None and snake_single is not None:
            raise serializers.ValidationError(
                {
                    "detail": "Передайте либо propertyId, "
                    "либо property_id, но не оба поля одновременно."
                }
            )

        if camel_many is not None and snake_many is not None:
            raise serializers.ValidationError(
                {
                    "detail": "Передайте либо propertyIds, "
                    "либо property_ids, но не оба поля одновременно."
                }
            )

        single_property_id = camel_single if camel_single is not None else snake_single
        property_ids = camel_many if camel_many is not None else snake_many

        if single_property_id is not None and property_ids is not None:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Передайте либо одно поле объекта "
                        "(propertyId/property_id), либо список "
                        "(propertyIds/property_ids), но не оба варианта."
                    )
                }
            )

        if property_ids is None:
            if single_property_id is None:
                raise serializers.ValidationError(
                    {
                        "propertyIds": [
                            "Передайте propertyIds для нового контракта "
                            "или propertyId/property_id для обратной совместимости."
                        ]
                    }
                )
            property_ids = [single_property_id]

        property_ids = list(dict.fromkeys(property_ids))
        if not property_ids:
            raise serializers.ValidationError(
                {"propertyIds": ["Нужно выбрать хотя бы один объект."]}
            )

        if start and start < now + min_offset:
            raise serializers.ValidationError(
                {
                    "start_date": [
                        f"Дата начала должна быть не менее чем на {min_offset} "
                        "от текущего момента."
                    ]
                }
            )

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_date": ["Дата окончания должна быть больше даты начала."]}
            )

        if start and end:
            dur = end - start
            if dur < min_dur:
                raise serializers.ValidationError(
                    {"end_date": [f"Продолжительность должна быть не менее {min_dur}."]}
                )
            if dur > max_dur:
                raise serializers.ValidationError(
                    {"end_date": [f"Продолжительность должна быть не более {max_dur}."]}
                )

        if mode == Auction.Mode.OPEN:
            if len(property_ids) != 1:
                raise serializers.ValidationError(
                    {
                        "propertyIds": [
                            "Для открытого аукциона нужно выбрать ровно один объект."
                        ]
                    }
                )

            if min_bid_increment is None:
                raise serializers.ValidationError(
                    {
                        "min_bid_increment": [
                            "Для открытого аукциона необходимо указать минимальный шаг ставки."
                        ]
                    }
                )

            if min_bid_increment < Decimal("1.00"):
                raise serializers.ValidationError(
                    {
                        "min_bid_increment": [
                            "Минимальный шаг ставки должен быть не меньше 1."
                        ]
                    }
                )

        elif mode == Auction.Mode.CLOSED:
            attrs["min_bid_increment"] = None

        attrs["property_ids"] = property_ids
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        property_ids = validated_data.pop("property_ids")

        with transaction.atomic():
            position_map = {
                prop_id: index for index, prop_id in enumerate(property_ids)
            }

            properties = list(
                Property.objects.select_for_update()
                .filter(
                    id__in=property_ids,
                    owner=request.user,
                    moderation_status=Property.ModerationStatuses.APPROVED,
                    status=Property.PropertyStatuses.PUBLISHED,
                )
                .only(
                    "id",
                    "reference_id",
                    "owner_id",
                    "type",
                    "project",
                    "rooms",
                    "purpose",
                    "area",
                    "property_class",
                    "delivery_date",
                    "price",
                    "address",
                )
            )

            properties.sort(key=lambda prop: position_map[prop.id])

            found_ids = {prop.id for prop in properties}
            missing_ids = [
                prop_id for prop_id in property_ids if prop_id not in found_ids
            ]
            if missing_ids:
                raise serializers.ValidationError(
                    {
                        "propertyIds": [
                            "Часть объектов не найдена, не принадлежит текущему девелоперу, "
                            "не одобрена модерацией или не опубликована."
                        ]
                    }
                )

            if validated_data["mode"] == Auction.Mode.CLOSED:
                validate_lot_compatibility(properties)

            busy_property_ids = set(
                Property.objects.filter(id__in=property_ids)
                .filter(
                    Q(open_auctions__status__in=BLOCKING_AUCTION_STATUSES)
                    | Q(lot_auctions__status__in=BLOCKING_AUCTION_STATUSES)
                )
                .values_list("id", flat=True)
                .distinct()
            )
            if busy_property_ids:
                raise serializers.ValidationError(
                    {
                        "propertyIds": [
                            "Некоторые объекты уже связаны с аукционом: "
                            f"{sorted(busy_property_ids)}"
                        ]
                    }
                )

            create_kwargs = {
                "owner": request.user,
                "status": Auction.Status.SCHEDULED,
                **validated_data,
            }

            # важно: для OPEN real_property должен быть установлен до insert
            if validated_data["mode"] == Auction.Mode.OPEN:
                create_kwargs["real_property"] = properties[0]

            auction = Auction.objects.create(**create_kwargs)

            AuctionProperty.objects.bulk_create(
                [AuctionProperty(auction=auction, property=prop) for prop in properties]
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
    myBid = serializers.SerializerMethodField()

    class Meta(AuctionListSerializer.Meta):
        fields = AuctionListSerializer.Meta.fields + ["bids", "myBid"]

    def _should_hide_property_price_for_broker(self, prop: Property) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            return False

        return (
            getattr(user, "role", None) == "broker"
            and prop.show_price_to_brokers is False
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if not data.get("properties"):
            return data

        hidden_property_ids = {
            prop.id
            for prop in instance.properties.all()
            if self._should_hide_property_price_for_broker(prop)
        }
        if not hidden_property_ids:
            return data

        for prop_data in data["properties"]:
            if prop_data.get("id") in hidden_property_ids:
                prop_data["price"] = None

        return data

    def get_bids(self, obj: Auction):
        request = self.context.get("request")

        if obj.mode == Auction.Mode.OPEN:
            qs = obj.bids.select_related("broker").order_by("-created_at")[:50]
            return BidSerializer(qs, many=True).data

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            is_admin = bool(
                getattr(user, "is_staff", False)
                or getattr(user, "is_superuser", False)
                or getattr(user, "is_admin", False)
            )
            if is_admin or obj.owner_id == user.id:
                qs = obj.bids.select_related("broker").order_by(
                    "-amount", "-created_at"
                )
                return BidSerializer(qs, many=True).data

        return []

    def get_myBid(self, obj: Auction):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            return None

        if obj.mode != Auction.Mode.CLOSED:
            return None

        bid = (
            obj.bids.filter(
                broker_id=user.id,
                is_sealed=True,
            )
            .select_related("broker")
            .order_by("-created_at")
            .first()
        )

        if not bid:
            return None

        return BidSerializer(bid).data


class BidCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
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
    bidIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def to_internal_value(self, data):
        normalized = {
            "bidIds": data.get("bidIds", data.get("bid_ids")),
        }
        ret = super().to_internal_value(normalized)
        return {"bid_ids": ret["bidIds"]}


class AuctionSelectWinnersSerializer(serializers.Serializer):
    brokerIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def to_internal_value(self, data):
        normalized = {
            "brokerIds": data.get("brokerIds", data.get("broker_ids")),
        }
        ret = super().to_internal_value(normalized)
        return {"broker_ids": ret["brokerIds"]}


class ClosedSelectWinnerSerializer(AuctionSelectWinnersSerializer):
    pass


class AuctionAssignmentItemSerializer(serializers.Serializer):
    brokerId = serializers.IntegerField(min_value=1)
    propertyIds = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def to_internal_value(self, data):
        normalized = {
            "brokerId": data.get("brokerId", data.get("broker_id")),
            "propertyIds": data.get("propertyIds", data.get("property_ids")),
        }
        ret = super().to_internal_value(normalized)
        return {
            "broker_id": ret["brokerId"],
            "property_ids": ret["propertyIds"],
        }


class AuctionAssignSerializer(serializers.Serializer):
    assignments = AuctionAssignmentItemSerializer(many=True)

    def validate(self, attrs):
        seen = set()
        for item in attrs["assignments"]:
            for property_id in item["property_ids"]:
                if property_id in seen:
                    raise serializers.ValidationError(
                        {
                            "assignments": (
                                f"Объект {property_id} указан более одного раза."
                            )
                        }
                    )
                seen.add(property_id)
        return attrs
