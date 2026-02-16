from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError

from .models import Property


class PropertyFilter(filters.FilterSet):
    status = filters.CharFilter(method="filter_status")

    # Filter by "district" via address substring (since address is a single field)
    address = filters.CharFilter(field_name="address", lookup_expr="icontains")

    # Price range filters
    price_min = filters.NumberFilter(field_name="price", lookup_expr="gte")
    price_max = filters.NumberFilter(field_name="price", lookup_expr="lte")

    # Optional: area range
    area_min = filters.NumberFilter(field_name="area", lookup_expr="gte")
    area_max = filters.NumberFilter(field_name="area", lookup_expr="lte")

    class Meta:
        model = Property
        fields = [
            "type",
            "property_class",
            "currency",
            "deadline",
            "address",
            "price_min",
            "price_max",
            "area_min",
            "area_max",
            "status",
        ]

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
