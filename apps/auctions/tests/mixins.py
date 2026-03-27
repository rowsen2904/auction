from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from auctions.models import Auction, Bid
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from properties.models import Property

User = get_user_model()


class AuctionTestMixin:
    BASE = "/api/v1/auctions/"
    MY_BASE = "/api/v1/auctions/my/"
    CANCEL_SUFFIX = "/cancel/"

    def rev(self, name: str, **kwargs) -> str:
        try:
            return reverse(name, kwargs=kwargs)
        except NoReverseMatch:
            return reverse(f"auctions:{name}", kwargs=kwargs)

    def create_users(self):
        self.dev1 = User.objects.create_user(
            email="dev1@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.dev2 = User.objects.create_user(
            email="dev2@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
        )
        self.broker1 = User.objects.create_user(
            email="broker1@test.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
        )
        self.broker2 = User.objects.create_user(
            email="broker2@test.com",
            password="StrongPass123!",
            role=User.Roles.BROKER,
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="StrongPass123!",
            role=User.Roles.DEVELOPER,
            is_active=True,
            is_staff=True,
            is_superuser=True,
        )

    def create_property(
        self,
        owner: User,
        *,
        address: str,
        p_type: str = "apartment",
        p_class: str = "comfort",
        area: Decimal = Decimal("50.00"),
        price: Decimal = Decimal("1000000.00"),
        status_val: str = "published",
    ) -> Property:
        return Property.objects.create(
            owner=owner,
            type=p_type,
            address=address,
            area=area,
            property_class=p_class,
            price=price,
            status=status_val,
        )

    def create_auction(
        self,
        *,
        owner: User,
        prop: Property,
        mode: str = Auction.Mode.OPEN,
        status_val: str = Auction.Status.SCHEDULED,
        start: timezone.datetime | None = None,
        end: timezone.datetime | None = None,
        min_price: Decimal = Decimal("1000.00"),
        min_bid_increment: Decimal | None = None,
        current_price: Decimal = Decimal("0.00"),
    ) -> Auction:
        now = timezone.now()
        start_dt = start or (now + timedelta(hours=2))
        end_dt = end or (now + timedelta(days=1))

        if mode == Auction.Mode.OPEN and min_bid_increment is None:
            min_bid_increment = Decimal("150000.00")

        if mode == Auction.Mode.CLOSED:
            min_bid_increment = None

        return Auction.objects.create(
            owner=owner,
            real_property=prop,
            mode=mode,
            min_price=min_price,
            min_bid_increment=min_bid_increment,
            start_date=start_dt,
            end_date=end_dt,
            status=status_val,
            current_price=current_price,
        )

    def create_bid(
        self,
        *,
        auction: Auction,
        broker: User,
        amount: Decimal,
        is_sealed: bool,
    ) -> Bid:
        return Bid.objects.create(
            auction=auction,
            broker=broker,
            amount=amount,
            is_sealed=is_sealed,
        )
