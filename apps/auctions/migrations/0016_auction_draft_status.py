# Auction draft status:
#   - extend Status with `draft`
#   - allow start_date / end_date to be NULL (drafts have no schedule)
#   - relax constraints so drafts skip the OPEN/CLOSED rules

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0015_auction_show_price_to_brokers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auction",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("scheduled", "Scheduled"),
                    ("active", "Active"),
                    ("finished", "Finished"),
                    ("cancelled", "Cancelled"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="scheduled",
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="auction",
            name="start_date",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="auction",
            name="end_date",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="auction",
            name="auc_end_gt_start",
        ),
        migrations.RemoveConstraint(
            model_name="auction",
            name="auc_open_requires_increment_and_property",
        ),
        migrations.AddConstraint(
            model_name="auction",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(start_date__isnull=True)
                    | models.Q(end_date__isnull=True)
                    | models.Q(end_date__gt=models.F("start_date"))
                ),
                name="auc_end_gt_start",
            ),
        ),
        migrations.AddConstraint(
            model_name="auction",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(status="draft")
                    | (
                        models.Q(mode="open")
                        & models.Q(min_bid_increment__isnull=False)
                        & models.Q(min_bid_increment__gte=Decimal("1.00"))
                        & models.Q(real_property__isnull=False)
                    )
                    | (
                        models.Q(mode="closed")
                        & models.Q(min_bid_increment__isnull=True)
                    )
                ),
                name="auc_open_requires_increment_and_property",
            ),
        ),
    ]
