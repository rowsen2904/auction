from __future__ import annotations

from django.contrib.auth import get_user_model
from django_filters import rest_framework as filters
from django_filters.filters import Q

User = get_user_model()


class UserFilter(filters.FilterSet):
    q = filters.CharFilter(method="filter_q")
    role = filters.CharFilter(field_name="role")
    is_active = filters.BooleanFilter(field_name="is_active")
    is_staff = filters.BooleanFilter(field_name="is_staff")

    date_joined_after = filters.IsoDateTimeFilter(
        field_name="date_joined", lookup_expr="gte"
    )
    date_joined_before = filters.IsoDateTimeFilter(
        field_name="date_joined", lookup_expr="lte"
    )

    broker_is_verified = filters.BooleanFilter(field_name="broker__is_verified")
    broker_status = filters.CharFilter(field_name="broker__verification_status")
    developer_company = filters.CharFilter(
        field_name="developer__company_name", lookup_expr="icontains"
    )

    class Meta:
        model = User
        fields = [
            "role",
            "is_active",
            "is_staff",
            "broker_is_verified",
            "broker_status",
            "developer_company",
        ]

    def filter_q(self, queryset, name, value):
        v = (value or "").strip()
        if not v:
            return queryset
        return queryset.filter(
            Q(email__icontains=v)
            | Q(first_name__icontains=v)
            | Q(last_name__icontains=v)
        )
