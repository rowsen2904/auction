from __future__ import annotations

from uuid import UUID

from auctions.models import Auction
from django.db.models import Q, QuerySet
from properties.models import Property
from rest_framework.exceptions import ValidationError

BLOCKING_AUCTION_STATUSES = (
    Auction.Status.SCHEDULED,
    Auction.Status.ACTIVE,
    Auction.Status.FINISHED,
)

POOL_MATCH_FIELDS = {
    Property.PropertyTypes.APARTMENT: [
        "type",
        "project",
        "rooms",
        "area",
        "property_class",
        "delivery_date",
    ],
    Property.PropertyTypes.HOUSE: [
        "type",
        "project",
        "rooms",
        "area",
        "property_class",
        "delivery_date",
    ],
    Property.PropertyTypes.TOWNHOUSE: [
        "type",
        "project",
        "rooms",
        "area",
        "property_class",
        "delivery_date",
    ],
    Property.PropertyTypes.COMMERCIAL: [
        "type",
        "project",
        "purpose",
        "commercial_subtype",
        "area",
        "property_class",
        "delivery_date",
    ],
    Property.PropertyTypes.LAND: [
        "type",
        "project",
        "area",
        "purpose",
        "property_class",
    ],
}


def parse_reference_id(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ValidationError({"reference_id": "Некорректный reference_id."})


def get_pool_match_fields(property_type: str) -> list[str]:
    fields = POOL_MATCH_FIELDS.get(property_type)
    if not fields:
        raise ValidationError(
            {"detail": f"Для типа {property_type} не настроены поля совместимости."}
        )
    return fields


def validate_lot_compatibility(properties: list[Property]) -> None:
    if len(properties) <= 1:
        return

    reference = properties[0]
    match_fields = get_pool_match_fields(reference.type)

    mismatches: list[str] = []

    for prop in properties[1:]:
        bad_fields = [
            field
            for field in match_fields
            if getattr(prop, field) != getattr(reference, field)
        ]
        if bad_fields:
            mismatches.append(
                f"property_id={prop.id} не совпадает по полям: {', '.join(bad_fields)}"
            )

    if mismatches:
        raise ValidationError(
            {
                "propertyIds": (
                    "Выбранные объекты несовместимы с эталонным объектом. "
                    + " | ".join(mismatches)
                )
            }
        )


def compatible_properties_qs(
    *, user, reference_id
) -> tuple[Property, QuerySet[Property]]:
    parsed_reference_id = parse_reference_id(reference_id)

    reference = (
        Property.objects.filter(
            owner=user,
            reference_id=parsed_reference_id,
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
            "commercial_subtype",
            "area",
            "property_class",
            "delivery_date",
            "price",
            "deadline",
            "address",
            "created_at",
        )
        .first()
    )

    if not reference:
        raise ValidationError(
            {
                "reference_id": (
                    "Эталонный объект не найден, не принадлежит текущему девелоперу "
                    "или недоступен для включения в лот."
                )
            }
        )

    match_fields = get_pool_match_fields(reference.type)
    filter_kwargs = {field: getattr(reference, field) for field in match_fields}

    qs = (
        Property.objects.filter(
            owner=user,
            moderation_status=Property.ModerationStatuses.APPROVED,
            status=Property.PropertyStatuses.PUBLISHED,
            **filter_kwargs,
        )
        .exclude(
            Q(open_auctions__status__in=BLOCKING_AUCTION_STATUSES)
            | Q(lot_auctions__status__in=BLOCKING_AUCTION_STATUSES)
        )
        .distinct()
        .order_by("-created_at")
    )

    return reference, qs
