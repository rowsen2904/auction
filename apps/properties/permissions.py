from rest_framework.permissions import BasePermission


class IsDeveloper(BasePermission):
    # Allow only authenticated users with developer role
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "is_developer", False)
        )


class IsPropertyOwner(BasePermission):
    # Owner = request.user is the Property.owner
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return obj.owner_id == user.id
