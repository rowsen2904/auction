from rest_framework.permissions import BasePermission


class IsBroker(BasePermission):
    """
    Broker can bid.
    If you also have "is_verified" flag — it will be enforced.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False

        if not getattr(user, "is_broker", False):
            return False

        # Optional: enforce verification if your user model has this flag
        if hasattr(user, "is_verified") and not getattr(user, "is_verified", False):
            return False

        return True


class IsDeveloper(BasePermission):
    # Allow only authenticated users with developer role
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and getattr(user, "is_developer", False)
        )


class IsAuctionOwner(BasePermission):
    def has_object_permission(self, request, view, obj):
        user = request.user
        return bool(user and user.is_authenticated and obj.owner_id == user.id)


class IsAuctionOwnerOrAdmin(BasePermission):
    """
    Allow action if:
    - user is the auction owner, OR
    - user is staff/superuser (admin)
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return True
        return obj.owner_id == user.id
