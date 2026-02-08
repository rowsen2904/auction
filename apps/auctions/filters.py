from django.utils import timezone
from django_filters import rest_framework as filters

from .models import Auction


class AuctionFilter(filters.FilterSet):
    mode = filters.ChoiceFilter(choices=Auction.Mode.choices)
    status = filters.ChoiceFilter(choices=Auction.Status.choices)

    property_id = filters.NumberFilter(field_name="real_property_id")

    owner_id = filters.NumberFilter(field_name="owner_id")

    active = filters.BooleanFilter(method="filter_active")

    ends_before = filters.IsoDateTimeFilter(field_name="end_date", lookup_expr="lte")
    ends_after = filters.IsoDateTimeFilter(field_name="end_date", lookup_expr="gte")

    starts_before = filters.IsoDateTimeFilter(
        field_name="start_date", lookup_expr="lte"
    )
    starts_after = filters.IsoDateTimeFilter(field_name="start_date", lookup_expr="gte")

    class Meta:
        model = Auction
        fields = [
            "mode",
            "status",
            "property_id",
            "owner_id",
            "active",
            "ends_before",
            "ends_after",
            "starts_before",
            "starts_after",
        ]

    def filter_active(self, qs, name, value):
        if not value:
            return qs

        now = timezone.now()
        return qs.filter(
            status=Auction.Status.ACTIVE,
            start_date__lte=now,
            end_date__gt=now,
        )
