from rest_framework.permissions import BasePermission


class IsPropertyOwner(BasePermission):
    # Owner = request.user is the Property.owner
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return obj.owner_id == user.id
