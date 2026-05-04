import django_filters

from .models import Deal


class DealFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Deal.Status.choices)
    obligation_status = django_filters.ChoiceFilter(
        choices=Deal.ObligationStatus.choices
    )
    auction_id = django_filters.NumberFilter(field_name="auction_id")
    real_property_id = django_filters.NumberFilter(field_name="real_property_id")
    broker_id = django_filters.NumberFilter(field_name="broker_id")
    developer_id = django_filters.NumberFilter(field_name="developer_id")

    date_from = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    date_to = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = Deal
        fields = [
            "status",
            "obligation_status",
            "auction_id",
            "real_property_id",
            "broker_id",
            "developer_id",
            "date_from",
            "date_to",
        ]
