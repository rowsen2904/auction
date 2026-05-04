from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError

from .models import Property


class BasePropertyFilter(filters.FilterSet):
    address = filters.CharFilter(field_name="address", lookup_expr="icontains")
    project = filters.CharFilter(field_name="project", lookup_expr="icontains")
    purpose = filters.CharFilter(field_name="purpose", lookup_expr="icontains")
    rooms = filters.NumberFilter(field_name="rooms")
    price_min = filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="price", lookup_expr="lte")
    area_min = filters.NumberFilter(field_name="area", lookup_expr="gte")
    area_max = filters.NumberFilter(field_name="area", lookup_expr="lte")
    delivery_date_before = filters.DateFilter(
        field_name="delivery_date",
        lookup_expr="lte",
    )
    delivery_date_after = filters.DateFilter(
        field_name="delivery_date",
        lookup_expr="gte",
    )

    class Meta:
        model = Property
        fields = [
            "type",
            "property_class",
            "deadline",
            "address",
            "project",
            "purpose",
            "commercial_subtype",
            "rooms",
            "price_min",
            "price_max",
            "area_min",
            "area_max",
            "delivery_date_before",
            "delivery_date_after",
        ]


class PublicPropertyFilter(BasePropertyFilter):
    status = filters.CharFilter(method="filter_status")

    class Meta(BasePropertyFilter.Meta):
        fields = BasePropertyFilter.Meta.fields + ["status"]

    def filter_status(self, qs, name, value):
        allowed = {
            Property.PropertyStatuses.PUBLISHED,
            Property.PropertyStatuses.SOLD,
        }

        value = (value or "").strip()

        if value not in allowed:
            raise ValidationError(
                {"status": f"Allowed values: {', '.join(sorted(allowed))}."}
            )
        return qs.filter(status=value)


class MyPropertyFilter(BasePropertyFilter):
    status = filters.CharFilter(field_name="status")

    class Meta(BasePropertyFilter.Meta):
        fields = BasePropertyFilter.Meta.fields + ["status"]


class PendingPropertyFilter(BasePropertyFilter):
    pass


class AdminPropertyFilter(BasePropertyFilter):
    moderation_status = filters.ChoiceFilter(
        field_name="moderation_status",
        choices=Property.ModerationStatuses.choices,
    )
    status = filters.CharFilter(field_name="status")
    owner_id = filters.NumberFilter(field_name="owner_id")

    class Meta(BasePropertyFilter.Meta):
        fields = BasePropertyFilter.Meta.fields + [
            "moderation_status",
            "status",
            "owner_id",
        ]
