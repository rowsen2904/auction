"""
Подробный smoke-тест Celery beat задач для тестировщика.

Запуск:
    python manage.py qa_celery_smoke

Что делает:
    Для каждой из 10 авто-задач печатает:
      - что задача делает
      - текущее состояние БД на момент запуска
      - возвращаемое значение
      - реальный delta в БД (что изменилось)
      - PASS если задача отработала без эксепшена; FAIL если упала.

Не модифицирует данные кроме как через сами задачи. Если в БД нет данных
которые задача должна обрабатывать — возвращает 0, и это нормально.
Чтобы увидеть «не нули», предварительно заведите тестовые данные через
шелл (см. конец этого файла, секция «Как заполнить данные»).
"""

from __future__ import annotations

import time
import traceback

from django.core.management.base import BaseCommand
from django.utils import timezone


# ANSI colors. Если терминал не поддерживает — будут просто escape-коды,
# но в обычном терминале все ок.
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"


def _hr(char: str = "═", color_name: str = "CYAN") -> str:
    # Look up color at call time (not definition time) so --plain override works.
    color = globals().get(color_name, "")
    reset = globals().get("RESET", "")
    return f"{color}{char * 78}{reset}"


class Command(BaseCommand):
    help = "Подробный smoke-test всех Celery beat задач. Печатает before/after."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tasks",
            nargs="*",
            help="Запустить только указанные задачи (по короткому имени). По умолчанию — все.",
        )
        parser.add_argument(
            "--plain",
            action="store_true",
            help="Отключить ANSI цвета и эмодзи (для CI / логов).",
        )

    def handle(self, *args, **options):
        if options["plain"] or options.get("no_color"):
            for k in ("RESET", "BOLD", "DIM", "GREEN", "RED", "YELLOW", "BLUE", "CYAN", "MAGENTA"):
                globals()[k] = ""

        # Импорты тут (а не на уровне модуля) — чтобы команду можно было
        # импортировать в обход Django setup тестами.
        from deals.models import Deal, DealLog
        from deals.tasks import check_overdue_deals, mark_failed_pending_deals
        from migtender.tasks import cleanup_beat_tasks
        from notifications.models import Notification
        from notifications.tasks import (
            notify_overdue_deals_task,
            send_admin_daily_deals_summary,
            send_admin_daily_payments_summary,
            send_developer_confirm_reminders,
            send_document_deadline_reminders,
        )
        from payments.models import DealSettlement
        from payments.tasks import (
            check_broker_payout_deadlines,
            check_developer_payment_deadlines,
        )

        # Каждый item: (короткое_имя, callable, описание, before_snapshot, after_snapshot)
        cases = [
            (
                "check_overdue_deals",
                check_overdue_deals,
                "Сделки с истёкшим document_deadline → obligation_status=overdue + лог.",
                lambda: {
                    "deals_pending_documents": Deal.objects.filter(
                        status=Deal.Status.PENDING_DOCUMENTS
                    ).count(),
                    "deals_already_overdue": Deal.objects.filter(
                        obligation_status=Deal.ObligationStatus.OVERDUE
                    ).count(),
                    "deals_with_past_deadline": Deal.objects.filter(
                        status=Deal.Status.PENDING_DOCUMENTS,
                        obligation_status=Deal.ObligationStatus.ACTIVE,
                        document_deadline__lt=timezone.now(),
                    ).count(),
                    "logs_marked_overdue": DealLog.objects.filter(
                        action=DealLog.Action.MARKED_OVERDUE
                    ).count(),
                },
            ),
            (
                "mark_failed_pending_deals",
                mark_failed_pending_deals,
                "Сделки в pending_documents старше 5 дней → status=failed + уведомление.",
                lambda: {
                    "deals_pending_documents": Deal.objects.filter(
                        status=Deal.Status.PENDING_DOCUMENTS
                    ).count(),
                    "deals_failed": Deal.objects.filter(
                        status=Deal.Status.FAILED
                    ).count(),
                    "logs_marked_failed": DealLog.objects.filter(
                        action=DealLog.Action.MARKED_FAILED
                    ).count(),
                },
            ),
            (
                "send_document_deadline_reminders",
                send_document_deadline_reminders,
                "Email брокеру за 3 / 1 / 0 дней до document_deadline.",
                lambda: {
                    "deals_pending_documents": Deal.objects.filter(
                        status=Deal.Status.PENDING_DOCUMENTS
                    ).count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "notify_overdue_deals_task",
                notify_overdue_deals_task,
                "Уведомление девелоперу о просроченных сделках.",
                lambda: {
                    "deals_overdue": Deal.objects.filter(
                        obligation_status=Deal.ObligationStatus.OVERDUE
                    ).count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "send_developer_confirm_reminders",
                send_developer_confirm_reminders,
                "Напоминание девелоперу подтвердить сделку.",
                lambda: {
                    "deals_developer_confirm": Deal.objects.filter(
                        status=Deal.Status.DEVELOPER_CONFIRM
                    ).count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "send_admin_daily_deals_summary",
                send_admin_daily_deals_summary,
                "Сводка админам — сколько сделок ждут проверки (admin_review).",
                lambda: {
                    "deals_admin_review": Deal.objects.filter(
                        status=Deal.Status.ADMIN_REVIEW
                    ).count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "send_admin_daily_payments_summary",
                send_admin_daily_payments_summary,
                "Сводка админам — сколько settlements ждут выплаты.",
                lambda: {
                    "settlements_unpaid": DealSettlement.objects.filter(
                        paid_to_broker=False
                    ).count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "check_broker_payout_deadlines",
                check_broker_payout_deadlines,
                "Дедлайны выплат брокеру: уведомления админам если близко/просрочено.",
                lambda: {
                    "settlements_total": DealSettlement.objects.count(),
                    "settlements_unpaid": DealSettlement.objects.filter(
                        paid_to_broker=False
                    ).count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "check_developer_payment_deadlines",
                check_developer_payment_deadlines,
                "Дедлайны оплат от девелопера: уведомления если близко/просрочено.",
                lambda: {
                    "settlements_total": DealSettlement.objects.count(),
                    "notifications_total": Notification.objects.count(),
                },
            ),
            (
                "cleanup_beat_tasks",
                cleanup_beat_tasks,
                "Очистка старых одноразовых задач django-celery-beat.",
                lambda: {
                    "note": "(только cleanup, без бизнес-данных)",
                },
            ),
        ]

        # Фильтр по --tasks
        only = options.get("tasks")
        if only:
            cases = [c for c in cases if c[0] in only]
            if not cases:
                self.stderr.write(
                    self.style.ERROR(
                        f"Ни одна задача не подошла под фильтр {only}. Доступные: "
                        + ", ".join(c[0] for c in cases)
                    )
                )
                return

        # Заголовок
        self.stdout.write("")
        self.stdout.write(_hr())
        self.stdout.write(
            f"{BOLD}{CYAN}  QA SMOKE — Celery beat tasks · {len(cases)} задач{RESET}"
        )
        self.stdout.write(
            f"{DIM}  Запущено: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}"
        )
        self.stdout.write(_hr())

        results = []

        for i, (name, fn, desc, snapshot_fn) in enumerate(cases, 1):
            self.stdout.write("")
            self.stdout.write(_hr("─", "BLUE"))
            self.stdout.write(
                f"{BOLD}{BLUE}[{i}/{len(cases)}] {name}{RESET}"
            )
            self.stdout.write(_hr("─", "BLUE"))
            self.stdout.write(f"{DIM}{desc}{RESET}")

            # Снимок до
            try:
                before = snapshot_fn()
            except Exception as e:
                before = {"_snapshot_error": repr(e)}

            self.stdout.write("")
            self.stdout.write(f"{YELLOW}  Состояние БД ДО:{RESET}")
            for k, v in before.items():
                self.stdout.write(f"    {k}: {BOLD}{v}{RESET}")

            # Запуск
            self.stdout.write("")
            self.stdout.write(f"{CYAN}  Запуск...{RESET}")
            t0 = time.perf_counter()
            error = None
            result = None
            try:
                result = fn()  # синхронно, без worker'а
            except Exception as e:
                error = e
                self.stdout.write(f"{RED}  {BOLD}ERROR:{RESET}{RED} {e}{RESET}")
                self.stdout.write(f"{RED}{traceback.format_exc()}{RESET}")
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Снимок после
            try:
                after = snapshot_fn()
            except Exception as e:
                after = {"_snapshot_error": repr(e)}

            self.stdout.write("")
            self.stdout.write(f"{CYAN}  Возвращаемое значение:{RESET}")
            self.stdout.write(f"    {BOLD}{result!r}{RESET}")

            # Diff
            self.stdout.write("")
            self.stdout.write(f"{YELLOW}  Состояние БД ПОСЛЕ:{RESET}")
            for k, v in after.items():
                before_v = before.get(k)
                if before_v != v:
                    diff = (
                        f"  {GREEN}({before_v} → {v}, +{(v - before_v) if isinstance(v, int) and isinstance(before_v, int) else '?'}){RESET}"
                        if isinstance(v, (int, float)) and isinstance(before_v, (int, float))
                        else f"  {GREEN}(было {before_v}, стало {v}){RESET}"
                    )
                else:
                    diff = f"  {DIM}(без изменений){RESET}"
                self.stdout.write(f"    {k}: {BOLD}{v}{RESET}{diff}")

            self.stdout.write("")
            self.stdout.write(
                f"{DIM}  Время выполнения: {elapsed_ms:.1f} ms{RESET}"
            )

            verdict = (
                f"{GREEN}{BOLD}✓ PASS{RESET}"
                if error is None
                else f"{RED}{BOLD}✗ FAIL{RESET}"
            )
            self.stdout.write(f"  {verdict}")

            results.append((name, error is None, error, elapsed_ms))

        # Итог
        self.stdout.write("")
        self.stdout.write(_hr())
        passed = sum(1 for _, ok, _, _ in results if ok)
        failed = len(results) - passed
        total_ms = sum(ms for _, _, _, ms in results)

        if failed == 0:
            self.stdout.write(
                f"  {GREEN}{BOLD}ИТОГ: все {passed}/{len(results)} задачи прошли успешно{RESET}"
            )
        else:
            self.stdout.write(
                f"  {RED}{BOLD}ИТОГ: {passed}/{len(results)} прошли, {failed} упали{RESET}"
            )
            for name, ok, err, _ in results:
                if not ok:
                    self.stdout.write(
                        f"    {RED}✗ {name}: {type(err).__name__}: {err}{RESET}"
                    )

        self.stdout.write(f"  {DIM}Суммарно: {total_ms:.1f} ms{RESET}")
        self.stdout.write(_hr())
        self.stdout.write("")

        # Подсказка как заполнить данные
        self.stdout.write(f"{DIM}{BOLD}Подсказка тестировщику:{RESET}")
        self.stdout.write(
            f"{DIM}  Если задачи возвращают нули — данных под их условия нет. Чтобы создать:{RESET}"
        )
        self.stdout.write(f"{DIM}    python manage.py qa_celery_seed   (отдельная команда — см. помощь по ней){RESET}")
        self.stdout.write(
            f"{DIM}  Или вручную через shell — примеры в начале этого файла.{RESET}"
        )
        self.stdout.write("")
