"""One-time command to create deals for existing finished auctions with winners."""

from django.core.management.base import BaseCommand
from django.db import transaction

from auctions.models import Auction, Bid
from deals.models import Deal
from deals.services import create_deal_from_bid


class Command(BaseCommand):
    help = "Create deals for finished auctions that have winners but no deals yet."

    def handle(self, *args, **options):
        auctions = Auction.objects.filter(
            status=Auction.Status.FINISHED,
            winner_bid_id__isnull=False,
        ).select_related("real_property")

        created = 0
        skipped = 0

        for auction in auctions:
            # Check if deal already exists for this bid
            if Deal.objects.filter(bid_id=auction.winner_bid_id).exists():
                skipped += 1
                continue

            try:
                with transaction.atomic():
                    bid = Bid.objects.get(id=auction.winner_bid_id)
                    deal = create_deal_from_bid(auction=auction, bid=bid)
                    created += 1
                    self.stdout.write(
                        f"  Created Deal #{deal.id} for Auction #{auction.id} "
                        f"(bid #{bid.id}, broker #{bid.broker_id})"
                    )
            except Exception as e:
                self.stderr.write(f"  Error for Auction #{auction.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone: {created} deals created, {skipped} skipped (already exist)."
            )
        )
