import decimal
import payments.models
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("deals", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("developer_commission", "Developer Commission"),
                            ("platform_commission", "Platform Commission"),
                        ],
                        db_index=True,
                        max_length=25,
                        verbose_name="Тип комиссии",
                    ),
                ),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        verbose_name="Сумма",
                    ),
                ),
                (
                    "rate",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=5,
                        verbose_name="Ставка (%)",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("paid", "Paid"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=10,
                        verbose_name="Статус",
                    ),
                ),
                (
                    "receipt_document",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=payments.models.payment_receipt_upload_to,
                        verbose_name="Чек/квитанция",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="deals.deal",
                    ),
                ),
            ],
            options={
                "verbose_name": "Выплата",
                "verbose_name_plural": "Выплаты",
                "ordering": ["-created_at"],
            },
        ),
        # Indexes
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["deal", "type"],
                name="pay_deal_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["status", "-created_at"],
                name="pay_status_created_idx",
            ),
        ),
        # Constraints
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.CheckConstraint(
                check=models.Q(amount__gte=decimal.Decimal("0.00")),
                name="pay_amount_gte_0",
            ),
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                fields=["deal", "type"],
                name="pay_unique_deal_type",
            ),
        ),
    ]
