from decimal import Decimal

from django.db import migrations, models
from django.db.models import Q


def fill_min_bid_increment(apps, schema_editor):
    Auction = apps.get_model("auctions", "Auction")

    Auction.objects.filter(mode="open", min_bid_increment__isnull=True).update(
        min_bid_increment=Decimal("150000.00")
    )

    Auction.objects.filter(mode="closed").update(min_bid_increment=None)


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0006_auction_unique_auction_per_property"),
    ]

    operations = [
        migrations.AddField(
            model_name="auction",
            name="min_bid_increment",
            field=models.DecimalField(
                max_digits=14,
                decimal_places=2,
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(fill_min_bid_increment, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="auction",
            constraint=models.CheckConstraint(
                check=(
                    (
                        Q(mode="open")
                        & Q(min_bid_increment__isnull=False)
                        & Q(min_bid_increment__gte=Decimal("1.00"))
                    )
                    | (Q(mode="closed") & Q(min_bid_increment__isnull=True))
                ),
                name="auc_open_requires_increment_closed_null",
            ),
        ),
    ]
