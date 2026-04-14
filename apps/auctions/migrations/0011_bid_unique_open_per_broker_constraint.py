from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0010_open_bid_unique_per_broker_and_updated_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="bid",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_sealed", False)),
                fields=("auction", "broker"),
                name="bid_unique_open_per_broker_per_auction",
            ),
        ),
    ]
