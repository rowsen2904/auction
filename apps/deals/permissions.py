from rest_framework.permissions import BasePermission


class IsDealBroker(BasePermission):
    """Object-level: request.user is the deal's broker."""

    def has_object_permission(self, request, view, obj):
        return obj.broker_id == request.user.id


class IsDealDeveloper(BasePermission):
    """Object-level: request.user is the deal's developer."""

    def has_object_permission(self, request, view, obj):
        return obj.developer_id == request.user.id
