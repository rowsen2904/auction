import decimal
import deals.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auctions", "0008_alter_auction_min_bid_increment"),
        ("properties", "0008_property_commission_rate"),
    ]

    operations = [
        migrations.CreateModel(
            name="Deal",
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
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        verbose_name="Сумма ставки",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_documents", "Pending Documents"),
                            ("admin_review", "Admin Review"),
                            ("developer_confirm", "Developer Confirm"),
                            ("confirmed", "Confirmed"),
                        ],
                        db_index=True,
                        default="pending_documents",
                        max_length=20,
                        verbose_name="Статус сделки",
                    ),
                ),
                (
                    "obligation_status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("fulfilled", "Fulfilled"),
                            ("overdue", "Overdue"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=10,
                        verbose_name="Статус обязательства",
                    ),
                ),
                (
                    "ddu_document",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=deals.models.deal_document_upload_to,
                        verbose_name="ДДУ",
                    ),
                ),
                (
                    "payment_proof_document",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=deals.models.deal_document_upload_to,
                        verbose_name="Подтверждение оплаты",
                    ),
                ),
                (
                    "broker_comment",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Комментарий брокера",
                    ),
                ),
                (
                    "admin_rejection_reason",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Причина отклонения (админ)",
                    ),
                ),
                (
                    "developer_rejection_reason",
                    models.TextField(
                        blank=True,
                        default="",
                        verbose_name="Причина отклонения (девелопер)",
                    ),
                ),
                (
                    "document_deadline",
                    models.DateTimeField(
                        db_index=True,
                        verbose_name="Дедлайн загрузки документов",
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
                    "auction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="deals",
                        to="auctions.auction",
                    ),
                ),
                (
                    "bid",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="deal",
                        to="auctions.bid",
                    ),
                ),
                (
                    "broker",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="broker_deals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "developer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="developer_deals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "real_property",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="deals",
                        to="properties.property",
                    ),
                ),
            ],
            options={
                "verbose_name": "Сделка",
                "verbose_name_plural": "Сделки",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DealLog",
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
                    "action",
                    models.CharField(
                        choices=[
                            ("created", "Created"),
                            ("ddu_uploaded", "DDU Uploaded"),
                            ("payment_proof_uploaded", "Payment Proof Uploaded"),
                            ("comment_added", "Comment Added"),
                            ("submitted_for_review", "Submitted for Review"),
                            ("admin_approved", "Admin Approved"),
                            ("admin_rejected", "Admin Rejected"),
                            ("developer_confirmed", "Developer Confirmed"),
                            ("developer_rejected", "Developer Rejected"),
                            ("marked_overdue", "Marked Overdue"),
                        ],
                        db_index=True,
                        max_length=30,
                    ),
                ),
                (
                    "detail",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "deal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="logs",
                        to="deals.deal",
                    ),
                ),
            ],
            options={
                "verbose_name": "Лог сделки",
                "verbose_name_plural": "Логи сделок",
                "ordering": ["-created_at"],
            },
        ),
        # Indexes
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(
                fields=["status", "-created_at"],
                name="deal_status_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(
                fields=["broker", "-created_at"],
                name="deal_broker_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(
                fields=["developer", "-created_at"],
                name="deal_dev_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="deal",
            index=models.Index(
                fields=["obligation_status", "document_deadline"],
                name="deal_oblig_deadline_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="deallog",
            index=models.Index(
                fields=["deal", "-created_at"],
                name="deallog_deal_created_idx",
            ),
        ),
        # Constraints
        migrations.AddConstraint(
            model_name="deal",
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=decimal.Decimal("0.00")),
                name="deal_amount_gt_0",
            ),
        ),
    ]
