"""
Засеять демо-данные так, чтобы каждая Celery beat задача обработала >0 объектов.

Запуск:
    python manage.py qa_celery_seed

После этого:
    python manage.py qa_celery_smoke

→ задачи вернут не-нули и обновят БД, тестировщик увидит реальные изменения.

Команда **не идемпотентна** в строгом смысле: повторный запуск создаст
новый набор демо-сделок. Чтобы вычистить — пометки идут с префиксом «QA-SEED».
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Seed demo data so every Celery beat task hits >0 objects."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dev-email",
            default="newdev2@test.com",
            help="Email девелопера, на которого вешать тестовые сделки.",
        )
        parser.add_argument(
            "--broker-email",
            default="rahimwws.me@gmail.com",
            help="Email брокера для тестовых сделок.",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Удалить ранее созданные QA-SEED данные и выйти.",
        )

    def handle(self, *args, **options):
        from auctions.models import Auction, Bid
        from deals.models import Deal
        from payments.models import DealSettlement
        from properties.models import Property

        User = get_user_model()
        now = timezone.now()
        seed_marker = "QA-SEED"

        try:
            dev = User.objects.get(email=options["dev_email"])
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f"Не найден девелопер {options['dev_email']}. "
                "Создай его руками или укажи --dev-email."
            ))
            return
        try:
            broker = User.objects.get(email=options["broker_email"])
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f"Не найден брокер {options['broker_email']}. "
                "Создай его руками или укажи --broker-email."
            ))
            return

        # ---------- Cleanup ----------
        if options["cleanup"]:
            qs = Property.objects.filter(owner=dev, project_comment__startswith=seed_marker)
            n_props = qs.count()
            # Cascade удалит связанные Deal / Bid / Auction / DealSettlement
            for prop in qs:
                Auction.objects.filter(real_property=prop).delete()
            qs.delete()
            self.stdout.write(self.style.SUCCESS(
                f"Удалено {n_props} QA-SEED объектов и связанные сущности."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"Сею данные: dev={dev.email} (id={dev.id}), broker={broker.email} (id={broker.id})"
        ))

        created = []

        # Helper: создать минимальную инфраструктуру property+auction+bid+deal
        def make_deal(*, scenario: str, property_kwargs: dict, deal_kwargs: dict) -> Deal:
            # Property
            prop = Property.objects.create(
                type=property_kwargs.get("type", "apartment"),
                address=property_kwargs.get("address", f"QA-SEED address [{scenario}]"),
                area=Decimal(property_kwargs.get("area", "50.00")),
                property_class=property_kwargs.get("property_class", "comfort"),
                price=Decimal(property_kwargs.get("price", "10000000.00")),
                status="published",
                moderation_status="approved",
                commission_rate=Decimal("2.50"),
                project=f"QA-SEED [{scenario}]",
                developer_name=getattr(dev.developer, "company_name", "QA"),
                floor=property_kwargs.get("floor", 1),
                house_number="",
                land_number="",
                project_comment=f"{seed_marker} {scenario}",
                owner=dev,
            )
            # Auction (finished, accepted)
            auction = Auction.objects.create(
                real_property=prop,
                owner=dev,
                mode="closed",
                show_price_to_brokers=True,
                min_price=prop.price,
                start_date=now - timedelta(days=10),
                end_date=now - timedelta(days=9),
                status="finished",
                current_price=prop.price,
                bids_count=1,
                owner_decision="accepted",
                owner_decided_at=now - timedelta(days=9),
            )
            # Bid
            bid = Bid.objects.create(
                auction=auction,
                broker=broker,
                amount=prop.price,
                is_sealed=True,
            )
            auction.winner_bid = bid
            auction.highest_bid = bid
            auction.save(update_fields=["winner_bid", "highest_bid"])
            # Deal
            deal = Deal.objects.create(
                auction=auction,
                bid=bid,
                broker=broker,
                developer=dev,
                real_property=prop,
                amount=prop.price,
                lot_bid_amount=prop.price,
                **deal_kwargs,
            )
            return deal

        # ---------- 1) Просроченная сделка для check_overdue_deals ----------
        d1 = make_deal(
            scenario="overdue",
            property_kwargs={"address": "QA-SEED Overdue, ул. Тестовая 1"},
            deal_kwargs={
                "status": Deal.Status.PENDING_DOCUMENTS,
                "obligation_status": Deal.ObligationStatus.ACTIVE,
                "document_deadline": now - timedelta(days=2),  # дедлайн в прошлом
            },
        )
        created.append(("overdue", d1))

        # ---------- 2) Зависшая на 6 дней для mark_failed_pending_deals ----------
        d2 = make_deal(
            scenario="stuck-6d",
            property_kwargs={"address": "QA-SEED Stuck, ул. Тестовая 2"},
            deal_kwargs={
                "status": Deal.Status.PENDING_DOCUMENTS,
                "obligation_status": Deal.ObligationStatus.ACTIVE,
                "document_deadline": now + timedelta(days=2),
            },
        )
        # Состарить created_at прямым SQL
        Deal.objects.filter(id=d2.id).update(created_at=now - timedelta(days=6))
        created.append(("stuck-6d", d2))

        # ---------- 3) Дедлайн через 3 дня для send_document_deadline_reminders ----------
        d3 = make_deal(
            scenario="deadline-3d",
            property_kwargs={"address": "QA-SEED Deadline-3d, ул. Тестовая 3"},
            deal_kwargs={
                "status": Deal.Status.PENDING_DOCUMENTS,
                "obligation_status": Deal.ObligationStatus.ACTIVE,
                "document_deadline": now + timedelta(days=3, hours=12),  # ровно 3д+
            },
        )
        created.append(("deadline-3d", d3))

        # ---------- 4) Дедлайн через 1 день — тоже для reminders ----------
        d4 = make_deal(
            scenario="deadline-1d",
            property_kwargs={"address": "QA-SEED Deadline-1d, ул. Тестовая 4"},
            deal_kwargs={
                "status": Deal.Status.PENDING_DOCUMENTS,
                "obligation_status": Deal.ObligationStatus.ACTIVE,
                "document_deadline": now + timedelta(days=1, hours=12),
            },
        )
        created.append(("deadline-1d", d4))

        # ---------- 5) В developer_confirm для send_developer_confirm_reminders ----------
        d5 = make_deal(
            scenario="awaiting-dev",
            property_kwargs={"address": "QA-SEED AwaitingDev, ул. Тестовая 5"},
            deal_kwargs={
                "status": Deal.Status.DEVELOPER_CONFIRM,
                "obligation_status": Deal.ObligationStatus.FULFILLED,
                "document_deadline": now + timedelta(days=10),
            },
        )
        # Состарить чтобы напоминалка точно сработала
        Deal.objects.filter(id=d5.id).update(updated_at=now - timedelta(days=2))
        created.append(("awaiting-dev", d5))

        # ---------- 6) В admin_review для send_admin_daily_deals_summary ----------
        d6 = make_deal(
            scenario="admin-review",
            property_kwargs={"address": "QA-SEED AdminReview, ул. Тестовая 6"},
            deal_kwargs={
                "status": Deal.Status.ADMIN_REVIEW,
                "obligation_status": Deal.ObligationStatus.FULFILLED,
                "document_deadline": now + timedelta(days=10),
            },
        )
        created.append(("admin-review", d6))

        # ---------- 7) Settlement с приближающимся payout-дедлайном ----------
        # Нужна confirmed-сделка с DealSettlement
        d7 = make_deal(
            scenario="settlement-pending",
            property_kwargs={"address": "QA-SEED Settlement, ул. Тестовая 7"},
            deal_kwargs={
                "status": Deal.Status.CONFIRMED,
                "obligation_status": Deal.ObligationStatus.FULFILLED,
                "document_deadline": now - timedelta(days=10),
            },
        )
        # Создать settlement (если ещё не создаётся хук-ом)
        settlement, _ = DealSettlement.objects.get_or_create(
            deal=d7,
            defaults={
                "broker_amount": Decimal("100000.00"),
                "broker_rate": Decimal("2.50"),
                "platform_amount": Decimal("40000.00"),
                "platform_rate": Decimal("0.40"),
                "total_from_developer": Decimal("140000.00"),
                "broker_payout_deadline": now + timedelta(hours=12),  # < 24h
                "developer_payment_deadline": now + timedelta(hours=18),
            },
        )
        created.append(("settlement-pending", d7))

        # Итог
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Создано {len(created)} тестовых сделок:"
        ))
        for label, deal in created:
            self.stdout.write(
                f"  Deal #{deal.id}  scenario={label}  status={deal.status}  "
                f"deadline={deal.document_deadline.strftime('%Y-%m-%d %H:%M')}"
            )
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "Теперь запусти: python manage.py qa_celery_smoke"
        ))
        self.stdout.write(self.style.NOTICE(
            "Чтобы убрать всё: python manage.py qa_celery_seed --cleanup"
        ))
