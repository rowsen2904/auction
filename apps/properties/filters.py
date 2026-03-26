from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError

from .models import Property


class BasePropertyFilter(filters.FilterSet):
    address = filters.CharFilter(field_name="address", lookup_expr="icontains")
    price_min = filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="price", lookup_expr="lte")
    area_min = filters.NumberFilter(field_name="area", lookup_expr="gte")
    area_max = filters.NumberFilter(field_name="area", lookup_expr="lte")

    class Meta:
        model = Property
        fields = [
            "type",
            "property_class",
            "deadline",
            "address",
            "price_min",
            "price_max",
            "area_min",
            "area_max",
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
