from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationQuerySet(models.QuerySet):
    def for_user(self, user):
        user_id = getattr(user, "pk", user)
        return self.filter(user_id=user_id)

    def unread(self):
        return self.filter(is_read=False)


class Notification(models.Model):
    class Category(models.TextChoices):
        SYSTEM = "system", "System"
        USER = "user", "User"
        PROPERTY = "property", "Property"
        AUCTION = "auction", "Auction"
        DEAL = "deal", "Deal"
        PAYMENT = "payment", "Payment"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    event_type = models.CharField(max_length=64, db_index=True)
    title = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)

    auction = models.ForeignKey(
        "auctions.Auction",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    deal = models.ForeignKey(
        "deals.Deal",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    payment = models.ForeignKey(
        "payments.Payment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    real_property = models.ForeignKey(
        "properties.Property",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )

    dedupe_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
    )
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="notif_user_read_created_idx",
            ),
            models.Index(
                fields=["category", "event_type"], name="notif_category_event_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"Notification #{self.id} user={self.user_id} event={self.event_type}"

    def mark_as_read(self) -> bool:
        if self.is_read:
            return False

        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])
        return True
