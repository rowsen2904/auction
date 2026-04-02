from __future__ import annotations

from typing import Iterable

from django.core.exceptions import FieldDoesNotExist
from django.db.models import QuerySet
from properties.models import Property

POOL_MATCH_FIELDS = {
    "apartment": [
        "type",
        "project",
        "rooms",
        "area",
        "property_class",
        "delivery_date",
    ],
    "house": [
        "type",
        "project",
        "rooms",
        "area",
        "property_class",
        "delivery_date",
    ],
    "townhouse": [
        "type",
        "project",
        "rooms",
        "area",
        "property_class",
        "delivery_date",
    ],
    "commercial": [
        "type",
        "project",
        "purpose",
        "area",
        "property_class",
        "delivery_date",
    ],
    "land": [
        "type",
        "project",
        "area",
        "purpose",
        "property_class",
    ],
}


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def property_reference_lookup_field() -> str:
    return "reference_id" if _model_has_field(Property, "reference_id") else "id"


def active_property_statuses() -> list[str]:
    statuses = getattr(Property, "PropertyStatuses", None)
    values: list[str] = []
    for name in ("ACTIVE", "PUBLISHED"):
        value = getattr(statuses, name, None) if statuses else None
        if value is not None:
            values.append(value)
    return values


def owner_active_properties_queryset(*, owner) -> QuerySet[Property]:
    qs = Property.objects.filter(owner=owner)
    status_values = active_property_statuses()
    if status_values:
        qs = qs.filter(status__in=status_values)
    return qs


def get_reference_property(*, owner, reference_id) -> Property | None:
    lookup_field = property_reference_lookup_field()
    return (
        owner_active_properties_queryset(owner=owner)
        .filter(**{lookup_field: reference_id})
        .first()
    )


def comparable_fields_for_property(prop: Property) -> list[str]:
    fields = POOL_MATCH_FIELDS.get(getattr(prop, "type", None), ["type"])
    return [field for field in fields if _model_has_field(Property, field)]


def compatibility_filter_kwargs(reference: Property) -> dict:
    kwargs = {}
    for field_name in comparable_fields_for_property(reference):
        kwargs[field_name] = getattr(reference, field_name)
    return kwargs


def get_compatible_properties(
    *, owner, reference_id
) -> tuple[Property | None, QuerySet[Property]]:
    reference = get_reference_property(owner=owner, reference_id=reference_id)
    if reference is None:
        return None, Property.objects.none()

    kwargs = compatibility_filter_kwargs(reference)
    qs = owner_active_properties_queryset(owner=owner).filter(**kwargs).order_by("id")
    return reference, qs


def ensure_properties_are_pool_compatible(properties: Iterable[Property]) -> None:
    props = list(properties)
    if len(props) <= 1:
        return

    reference = props[0]
    fields = comparable_fields_for_property(reference)

    mismatches: list[int] = []
    mismatch_details: dict[int, list[str]] = {}

    for prop in props[1:]:
        different_fields: list[str] = []
        for field_name in fields:
            if getattr(prop, field_name, None) != getattr(reference, field_name, None):
                different_fields.append(field_name)

        if different_fields:
            mismatches.append(prop.id)
            mismatch_details[prop.id] = different_fields

    if mismatches:
        raise ValueError(
            {
                "propertyIds": (
                    "Для закрытого аукциона все объекты в лоте должны быть совместимы "
                    f"с первым выбранным объектом. Несовместимые объекты: {mismatch_details}"
                )
            }
        )
