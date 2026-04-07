# Notifications module — полная документация для backend и frontend

Документация для модуля персональных уведомлений в проекте **MIG Tender**.

Стек: **Django + PostgreSQL + Redis + Celery + Channels + SimpleJWT**.

Этот модуль решает две задачи:

1. **Хранит уведомления в базе** — пользователь видит историю уведомлений даже после перезагрузки приложения.
2. **Пушит новые уведомления в реальном времени по WebSocket** — фронт получает событие сразу после изменения бизнес-состояния.

---

## 1. Что реализовано

### 1.1. Для чего нужен модуль

Уведомления покрывают бизнес-события из ТЗ для трёх ролей:

- **Брокер**
- **Девелопер**
- **Админ**

События приходят при:

- регистрации брокера
- создании объекта на модерацию
- завершении аукциона
- выборе/невыборе победителя в закрытом аукционе
- создании сделки
- отправке сделки на проверку
- одобрении/отклонении сделки админом
- подтверждении/отклонении сделки девелопером
- создании выплат
- оплате выплаты
- дедлайн-напоминаниях
- просрочке обязательства
- ежедневных сводках для админа

### 1.2. Как устроен модуль

Модуль состоит из следующих частей:

- `notifications/models.py` — модель `Notification`
- `notifications/services.py` — единая бизнес-логика создания уведомлений
- `notifications/realtime.py` — отправка событий в Channels group конкретного пользователя
- `notifications/consumers.py` — WebSocket consumer `ws/notifications/`
- `notifications/views.py` — REST API списка и read-операций
- `notifications/tasks.py` — Celery-задачи для reminder/digest уведомлений
- `notifications/routing.py` — websocket route

Главный принцип: **уведомление сначала сохраняется в БД, потом после успешного commit отправляется в websocket**.

Это важно, чтобы фронт не получил уведомление о событии, которого ещё нет в базе.

---

## 2. Архитектура работы

### 2.1. Поток создания уведомления

Общий сценарий такой:

1. В проекте происходит бизнес-событие.
   Например:
   - брокер отправил сделку на проверку
   - админ одобрил документы
   - аукцион завершился
2. В соответствующем `view`, `service` или `task` вызывается функция из `notifications.services`.
3. Создаётся запись `Notification` в БД.
4. Через `transaction.on_commit(...)` вызывается websocket broadcast.
5. Клиент, подписанный на `ws/notifications/`, получает событие.
6. Если клиент был офлайн, он увидит уведомление позже через snapshot или REST list.

### 2.2. Почему не сигналы

Основная логика уведомлений сознательно не сделана через Django signals.

Причина:

- в проекте уже есть хорошие и понятные точки входа в бизнес-логику: `views.py`, `services.py`, `tasks.py`
- уведомления должны отправляться в чёткий момент бизнес-перехода, а не “где-то после save”
- так проще отлаживать и проще объяснять фронтенду и другим backend-разработчикам, откуда и почему пришло уведомление

---

## 3. Аутентификация WebSocket

В проекте WebSocket аутентифицируется через **SimpleJWT access token**, который передаётся в query string.

Ты прислал свой актуальный middleware, и модуль документации ниже уже учитывает именно его.

### 3.1. Middleware

```python
class JwtAuthMiddleware(BaseMiddleware):
    """
    Authenticate WebSocket connections using SimpleJWT access token passed via query string:
      ws://.../ws/auctions/<id>/?token=...
    """
```

То же самое применяется и к `ws/notifications/`.

### 3.2. Как подключаться с фронта

#### Development

```text
ws://localhost:8000/ws/notifications/?token=<ACCESS_TOKEN>
```

#### Production

```text
wss://api.example.com/ws/notifications/?token=<ACCESS_TOKEN>
```

### 3.3. Важные моменты для фронта

- использовать нужно именно **access token**, не refresh token
- если access token истёк, сокет нужно переподключать уже с новым access token
- в production использовать только `wss://`
- токен передаётся в query string, поэтому важно:
  - не логировать URL на клиенте без необходимости
  - использовать короткоживущий access token
  - не вставлять такой URL в публичные логи или crash reports

---

## 4. ASGI и routing

Текущий проектный `asgi.py`, который ты прислал, уже правильно подходит под модуль уведомлений:

```python
from .middleware import JwtAuthMiddleware
from auctions.routing import websocket_urlpatterns as auction_ws_urlpatterns
from notifications.routing import websocket_urlpatterns as notification_ws_urlpatterns
from channels.routing import ProtocolTypeRouter, URLRouter

websocket_urlpatterns = [
    *auction_ws_urlpatterns,
    *notification_ws_urlpatterns,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
```

### 4.1. Endpoint уведомлений

```text
/ws/notifications/
```

Итоговый URL подключения:

```text
ws://<host>/ws/notifications/?token=<access_token>
```

---

## 5. Модель уведомления

### 5.1. Поля `Notification`

```python
class Notification(models.Model):
    user
    category
    event_type
    title
    message
    data
    auction
    deal
    payment
    real_property
    dedupe_key
    is_read
    read_at
    created_at
```

### 5.2. Что означает каждое поле

- `user` — владелец уведомления
- `category` — верхний тип сущности:
  - `system`
  - `user`
  - `property`
  - `auction`
  - `deal`
  - `payment`
- `event_type` — конкретный тип события, на который фронт может опираться для логики
- `title` — короткий заголовок, сейчас чаще пустой, но оставлен на будущее
- `message` — человекочитаемый текст уведомления для UI
- `data` — дополнительный структурированный payload для фронта
- `auction`, `deal`, `payment`, `real_property` — связи на предмет уведомления
- `dedupe_key` — защита от дублей для cron/reminder/digest событий
- `is_read` — прочитано или нет
- `read_at` — дата прочтения
- `created_at` — дата создания

### 5.3. Сериализованный объект, который получает фронт

```json
{
  "id": 101,
  "category": "deal",
  "event_type": "admin_approved",
  "title": "",
  "message": "Админ одобрил документы по ул. Гагарина 12. Ожидаем подтверждения девелопера",
  "data": {
    "deal_id": 55,
    "property_id": 8
  },
  "auction_id": 44,
  "deal_id": 55,
  "payment_id": null,
  "real_property_id": 8,
  "is_read": false,
  "read_at": null,
  "created_at": "2026-04-07T12:25:10+05:00"
}
```

### 5.4. Рекомендация для фронта

Для переходов по экрану лучше ориентироваться не только на `message`, а на связку:

- `event_type`
- `category`
- `data`
- `auction_id / deal_id / payment_id / real_property_id`

`message` нужно использовать как готовый текст для UI, а не как единственный источник логики.

---

## 6. WebSocket API

## 6.1. Подключение

После успешного подключения сервер сразу отправляет **snapshot** последних уведомлений пользователя.

### Событие от сервера: `notifications_snapshot`

```json
{
  "type": "notifications_snapshot",
  "notifications": [
    {
      "id": 101,
      "category": "deal",
      "event_type": "admin_approved",
      "title": "",
      "message": "Админ одобрил документы по ул. Гагарина 12. Ожидаем подтверждения девелопера",
      "data": {
        "deal_id": 55,
        "property_id": 8
      },
      "auction_id": 44,
      "deal_id": 55,
      "payment_id": null,
      "real_property_id": 8,
      "is_read": false,
      "read_at": null,
      "created_at": "2026-04-07T12:25:10+05:00"
    }
  ],
  "unread_count": 5
}
```

Что важно:

- snapshot отдаёт **последние 50** уведомлений
- `unread_count` считается по всем непрочитанным уведомлениям пользователя, а не только по этим 50

## 6.2. События от сервера

### `notification_created`

Приходит, когда создано новое уведомление.

```json
{
  "type": "notification_created",
  "notification": {
    "id": 102,
    "category": "payment",
    "event_type": "payout_paid",
    "title": "",
    "message": "Выплата выполнена: 5000.00. Чек доступен в «Мои выплаты»",
    "data": {
      "payment_id": 77,
      "deal_id": 55,
      "amount": "5000.00"
    },
    "auction_id": null,
    "deal_id": 55,
    "payment_id": 77,
    "real_property_id": 8,
    "is_read": false,
    "read_at": null,
    "created_at": "2026-04-07T12:35:10+05:00"
  },
  "unread_count": 6
}
```

### `notification_read`

Приходит, когда конкретное уведомление отмечено как прочитанное.

```json
{
  "type": "notification_read",
  "notification_id": 102,
  "read_at": "2026-04-07T12:40:00+05:00",
  "unread_count": 5
}
```

### `notifications_read_all`

Приходит, когда пользователь отметил все уведомления как прочитанные.

```json
{
  "type": "notifications_read_all",
  "notification_ids": [102, 101, 100],
  "read_at": "2026-04-07T12:41:00+05:00",
  "unread_count": 0
}
```

### `pong`

Ответ на ping.

```json
{
  "type": "pong"
}
```

### `error`

Ошибка протокола.

```json
{
  "type": "error",
  "detail": "Неизвестный тип сообщения."
}
```

---

## 7. Сообщения от клиента в WebSocket

## 7.1. `ping`

Можно использовать как heartbeat на клиенте.

```json
{
  "type": "ping"
}
```

Ответ:

```json
{
  "type": "pong"
}
```

## 7.2. `mark_read`

Отметить одно уведомление как прочитанное.

```json
{
  "type": "mark_read",
  "notification_id": 102
}
```

Допускается и camelCase-ключ:

```json
{
  "type": "mark_read",
  "notificationId": 102
}
```

Что происходит дальше:

- если уведомление существует и принадлежит текущему пользователю, оно отмечается как прочитанное
- после commit сервер рассылает `notification_read`
- если уведомление уже было прочитано, нового websocket-события не будет

## 7.3. `mark_all_read`

Отметить все уведомления пользователя как прочитанные.

```json
{
  "type": "mark_all_read"
}
```

После commit сервер пришлёт:

```json
{
  "type": "notifications_read_all",
  ...
}
```

---

## 8. Закрытие соединения и коды

### `4401`

Пользователь не аутентифицирован.

Когда бывает:

- нет `token` в query string
- токен невалиден
- токен истёк

### Поведение фронта

- обновить access token стандартным refresh flow
- пересоздать websocket с новым access token

Дополнительных специальных close-кодов именно для notification consumer сейчас нет.

---

## 9. REST API уведомлений

REST нужен для:

- экрана “Все уведомления”
- initial fetch без websocket
- fallback, если сокет временно недоступен
- read-операций вне realtime-сессии

## 9.1. Список уведомлений

### Request

```http
GET /api/v1/notifications/
Authorization: Bearer <access_token>
```

### Response

Если в проекте включена глобальная DRF pagination, ответ будет пагинированным в стандартном формате проекта.
Если глобальной pagination нет — вернётся обычный массив `NotificationSerializer`.

Пример без пагинации:

```json
[
  {
    "id": 101,
    "category": "deal",
    "event_type": "admin_approved",
    "title": "",
    "message": "Админ одобрил документы по ул. Гагарина 12. Ожидаем подтверждения девелопера",
    "data": {
      "deal_id": 55,
      "property_id": 8
    },
    "auction_id": 44,
    "deal_id": 55,
    "payment_id": null,
    "real_property_id": 8,
    "is_read": false,
    "read_at": null,
    "created_at": "2026-04-07T12:25:10+05:00"
  }
]
```

## 9.2. Получить unread count

### Request

```http
GET /api/v1/notifications/unread-count/
Authorization: Bearer <access_token>
```

### Response

```json
{
  "unread_count": 5
}
```

## 9.3. Отметить одно уведомление как прочитанное

### Request

```http
PATCH /api/v1/notifications/mark-read/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "notification_id": 101
}
```

### Response

```json
{
  "detail": "OK"
}
```

После этого, если у пользователя открыт websocket, он также получит realtime-событие `notification_read`.

## 9.4. Отметить все уведомления как прочитанные

### Request

```http
PATCH /api/v1/notifications/mark-all-read/
Authorization: Bearer <access_token>
```

### Response

```json
{
  "notification_ids": [101, 100, 99]
}
```

После этого, если websocket открыт, пользователь дополнительно получит `notifications_read_all`.

---

## 10. Event types, которые должен знать фронт

Ниже перечислены все текущие `event_type`, которые реально создаются в `notifications/services.py`.

## 10.1. User / Property

### `new_broker_registered`

Кому приходит:
- админ

Когда:
- зарегистрировался новый брокер

Смысл:
- у админа появилась новая заявка на верификацию брокера

`data`:

```json
{
  "broker_user_id": 15
}
```

### `new_property_pending`

Кому приходит:
- админ

Когда:
- девелопер создал объект, который ушёл на модерацию

`data`:

```json
{
  "property_id": 8,
  "owner_id": 21
}
```

## 10.2. Auction

### `auction_won`

Кому приходит:
- брокер

Когда:
- создана сделка для победившего брокера

То есть для open-аукциона — после завершения аукциона и auto-create deal, а для closed — после выбора/assign и создания deal.

`data`:

```json
{
  "auction_id": 44,
  "deal_id": 55,
  "property_id": 8
}
```

### `auction_not_selected`

Кому приходит:
- брокеры, которые участвовали в закрытом аукционе, но не были выбраны

Когда:
- в закрытом аукционе выполнен выбор победителей

`data`:

```json
{
  "auction_id": 44
}
```

### `auction_finished_open`

Кому приходит:
- девелопер-владелец аукциона

Когда:
- завершён open-аукцион

`data`:

```json
{
  "auction_id": 44,
  "winner_bid_id": 71
}
```

`winner_bid_id` может быть `null`, если победитель не определён.

### `auction_finished_closed`

Кому приходит:
- девелопер-владелец аукциона

Когда:
- завершён closed-аукцион

`data`:

```json
{
  "auction_id": 44,
  "bids_count": 5
}
```

## 10.3. Deal / Deadline / Review

### `documents_deadline_3d`

Кому приходит:
- брокер

Когда:
- до `document_deadline` осталось 3 дня

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "days_left": 3
}
```

### `documents_deadline_1d`

Кому приходит:
- брокер

Когда:
- до `document_deadline` остался 1 день

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "days_left": 1
}
```

### `obligation_overdue`

Кому приходит:
- брокер
- все админы

Когда:
- обязательство по сделке стало `OVERDUE`

`data` для брокера:

```json
{
  "deal_id": 55,
  "property_id": 8
}
```

`data` для админа:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "broker_id": 15
}
```

### `deal_submitted_for_review`

Кому приходит:
- все админы
- девелопер

Когда:
- брокер загрузил документы и отправил сделку на review

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "broker_id": 15
}
```

### `admin_approved`

Кому приходит:
- брокер

Когда:
- админ одобрил документы

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8
}
```

### `developer_needs_confirm`

Кому приходит:
- девелопер

Когда:
- после admin approve, девелопер должен подтвердить сделку

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8
}
```

### `admin_rejected`

Кому приходит:
- брокер

Когда:
- админ отклонил документы

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "reason": "Нечитаемый документ"
}
```

### `developer_confirm_reminder`

Кому приходит:
- девелопер

Когда:
- сделка слишком долго висит в `developer_confirm`

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "waiting_days": 3
}
```

### `developer_confirmed`

Кому приходит:
- брокер
- все админы

Когда:
- девелопер подтвердил сделку

`data` для брокера:

```json
{
  "deal_id": 55,
  "property_id": 8
}
```

`data` для админа:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "developer_id": 21
}
```

### `developer_rejected`

Кому приходит:
- брокер
- все админы

Когда:
- девелопер отклонил сделку

`data`:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "reason": "Неверная сумма"
}
```

## 10.4. Payment

### `payout_created`

Кому приходит:
- брокер
- девелопер

Когда:
- после подтверждения сделки созданы выплаты

`data` для брокера:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "total": "5400.00",
  "from_developers": "5000.00",
  "from_platform": "400.00"
}
```

`data` для девелопера:

```json
{
  "deal_id": 55,
  "property_id": 8,
  "amount": "5000.00",
  "rate": "2.50"
}
```

### `payout_paid`

Кому приходит:
- брокер
- девелопер

Когда:
- админ загрузил чек для `platform_commission`, и выплата отмечена как `PAID`

`data` для брокера:

```json
{
  "payment_id": 77,
  "deal_id": 55,
  "amount": "5000.00"
}
```

`data` для девелопера:

```json
{
  "payment_id": 77,
  "deal_id": 55,
  "amount": "5000.00",
  "broker_id": 15
}
```

## 10.5. Daily summaries

### `daily_deals_summary`

Кому приходит:
- админ

Когда:
- ежедневная утренняя сводка по сделкам на review

`data`:

```json
{
  "count": 4,
  "date": "2026-04-07"
}
```

### `daily_payments_summary`

Кому приходит:
- админ

Когда:
- ежедневная утренняя сводка по ожидающим выплатам

`data`:

```json
{
  "count": 7,
  "total": "12500.00",
  "date": "2026-04-07"
}
```

---

## 11. Что должен делать фронт

## 11.1. Базовый сценарий интеграции

1. После логина получить `access token`
2. Открыть websocket:

```text
/ws/notifications/?token=<access_token>
```

3. После `notifications_snapshot`:
   - сохранить массив уведомлений в store
   - сохранить `unread_count`
4. На `notification_created`:
   - добавить уведомление в начало списка
   - обновить badge/unread count
5. На `notification_read`:
   - отметить один элемент как прочитанный
   - обновить unread count
6. На `notifications_read_all`:
   - отметить все уведомления как прочитанные
   - обновить unread count
7. При истечении токена:
   - обновить access token
   - переподключить websocket

## 11.2. Рекомендуемая логика UI

Удобно разделить уведомления по экрану:

- общая лента уведомлений
- badge на табе/иконке
- локальные редиректы по типу события

Пример маршрутизации:

- если `deal_id` не `null` → переход на экран сделки
- если `payment_id` не `null` → переход на экран выплат / детали выплаты
- если `auction_id` не `null` → переход на экран аукциона
- если `real_property_id` не `null` → переход на экран объекта

## 11.3. Рекомендуемая store-структура

Например:

```ts
interface NotificationItem {
  id: number;
  category: string;
  event_type: string;
  title: string;
  message: string;
  data: Record<string, unknown>;
  auction_id: number | null;
  deal_id: number | null;
  payment_id: number | null;
  real_property_id: number | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}

interface NotificationsState {
  items: NotificationItem[];
  unreadCount: number;
  isConnected: boolean;
}
```

## 11.4. Рекомендации по dedupe на фронте

Хотя backend сам защищает часть событий через `dedupe_key`, фронту всё равно лучше:

- хранить уведомления по `id`
- при получении `notification_created` не вставлять элемент второй раз, если такой `id` уже есть

---

## 12. Пример клиента на фронте

Ниже пример на TypeScript/React Native/Web.

```ts
class NotificationsSocket {
  private socket: WebSocket | null = null;

  connect(accessToken: string) {
    const base = "wss://api.example.com/ws/notifications/";
    this.socket = new WebSocket(`${base}?token=${accessToken}`);

    this.socket.onopen = () => {
      console.log("notifications ws connected");
    };

    this.socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);

      switch (payload.type) {
        case "notifications_snapshot":
          // set items + unread_count
          break;

        case "notification_created":
          // prepend notification, update unread_count
          break;

        case "notification_read":
          // mark one as read
          break;

        case "notifications_read_all":
          // mark all as read
          break;

        case "pong":
          break;

        case "error":
          console.warn("notifications ws error payload", payload.detail);
          break;
      }
    };

    this.socket.onclose = (event) => {
      console.log("notifications ws closed", event.code);
      // тут можно запускать reconnect policy
    };

    this.socket.onerror = (error) => {
      console.error("notifications ws transport error", error);
    };
  }

  ping() {
    this.socket?.send(JSON.stringify({ type: "ping" }));
  }

  markRead(notificationId: number) {
    this.socket?.send(
      JSON.stringify({ type: "mark_read", notification_id: notificationId })
    );
  }

  markAllRead() {
    this.socket?.send(JSON.stringify({ type: "mark_all_read" }));
  }

  disconnect() {
    this.socket?.close();
    this.socket = null;
  }
}
```

---

## 13. Backend integration points

Ниже перечислены места, в которые этот модуль уже рассчитан встраиваться.

## 13.1. `apps/users/views.py`

### Событие
`new_broker_registered`

### Когда вызывать
После успешной регистрации брокера.

### Вызов
```python
from notifications.services import notify_new_broker_registered

notify_new_broker_registered(broker_user=user)
```

## 13.2. `properties/views.py`

### Событие
`new_property_pending`

### Когда вызывать
После создания объекта, если он не draft и уходит на модерацию.

### Вызов
```python
from notifications.services import notify_new_property_pending

notify_new_property_pending(real_property=prop)
```

## 13.3. `auctions/tasks.py`

### События
- `auction_finished_open`
- `auction_finished_closed`

### Когда вызывать
После завершения аукциона в `finish_auction()`.

## 13.4. `auctions/services/assignments.py`

### Событие
`auction_not_selected`

### Когда вызывать
После выбора победителей закрытого аукциона.

## 13.5. `deals/services.py`

### События
- `auction_won`
- `deal_submitted_for_review`
- `payout_created`

### Когда вызывать
- после `create_deal_from_bid(...)`
- после `submit_deal_for_review(...)`
- после `create_payments_for_deal(...)`

## 13.6. `deals/views.py`

### События
- `admin_approved`
- `developer_needs_confirm`
- `admin_rejected`
- `developer_confirmed`
- `developer_rejected`

### Когда вызывать
В соответствующих view-методах после успешного перехода статуса сделки.

## 13.7. `payments/views.py`

### Событие
`payout_paid`

### Когда вызывать
После того, как payment помечен как `PAID`.

---

## 14. Celery и cron-задачи

В модуле есть пять периодических задач:

- `send_document_deadline_reminders`
- `notify_overdue_deals_task`
- `send_developer_confirm_reminders`
- `send_admin_daily_deals_summary`
- `send_admin_daily_payments_summary`

### Пример `CELERY_BEAT_SCHEDULE`

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE |= {
    "notifications-document-deadline-reminders": {
        "task": "notifications.tasks.send_document_deadline_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "notifications-overdue-deals": {
        "task": "notifications.tasks.notify_overdue_deals_task",
        "schedule": crontab(hour=9, minute=10),
    },
    "notifications-developer-confirm-reminders": {
        "task": "notifications.tasks.send_developer_confirm_reminders",
        "schedule": crontab(hour=10, minute=0),
    },
    "notifications-admin-daily-deals-summary": {
        "task": "notifications.tasks.send_admin_daily_deals_summary",
        "schedule": crontab(hour=8, minute=0),
    },
    "notifications-admin-daily-payments-summary": {
        "task": "notifications.tasks.send_admin_daily_payments_summary",
        "schedule": crontab(hour=8, minute=5),
    },
}
```

### Настройка reminder-а девелопера

В `settings.py`:

```python
NOTIFICATION_DEVELOPER_CONFIRM_REMINDER_DAYS = 3
```

Это означает:

- если сделка висит в `developer_confirm` минимум 3 дня, девелоперу уходит reminder

---

## 15. Installation checklist

### 15.1. Приложение

В `settings.py`:

```python
INSTALLED_APPS += [
    "notifications",
]
```

### 15.2. Root urls

В корневом `urls.py`:

```python
path("api/v1/notifications/", include("notifications.urls")),
```

### 15.3. Websocket routing

Подключить `notifications.routing.websocket_urlpatterns` в общий websocket router.

### 15.4. Middleware

Убедиться, что `JwtAuthMiddleware` реально оборачивает `URLRouter`.

### 15.5. Миграции

```bash
python manage.py makemigrations notifications
python manage.py migrate
```

### 15.6. Channels / Redis

Убедиться, что:

- Channels настроен
- channel layer работает
- Redis доступен
- Celery worker и Celery beat запущены

---

## 16. Поведение read-операций

## 16.1. Через WebSocket

Если фронт вызывает `mark_read` или `mark_all_read` через WebSocket:

- БД обновляется
- после commit приходит websocket-событие
- UI синхронизируется сам по факту backend-подтверждения

## 16.2. Через REST

Если фронт использует REST для read-операций:

- БД обновляется
- если websocket открыт, клиент тоже получит realtime-событие

Иными словами, **REST и WebSocket не конфликтуют**.

---

## 17. Как фронту правильно обрабатывать события

### Для бейджа уведомлений

Источник истины:
- `unread_count` из snapshot
- `unread_count` из realtime-событий
- fallback: `GET /api/v1/notifications/unread-count/`

### Для списка уведомлений

Источник истины:
- snapshot после подключения
- дальше дельты по websocket
- fallback и ручной refresh через `GET /api/v1/notifications/`

### Для экранов перехода

Использовать:
- `event_type`
- `deal_id`, `payment_id`, `auction_id`, `real_property_id`
- `data`

Не завязывать навигацию на текст `message`.

---

## 18. Ограничения текущей реализации

1. Snapshot при подключении ограничен **50 последними уведомлениями**.
2. `title` пока почти не используется — UI должен в первую очередь опираться на `message`.
3. Для `mark_read` по websocket, если уведомление уже прочитано, отдельного ack сейчас не приходит.
4. Notification list view использует общую пагинацию проекта, если она включена глобально.
5. `payout_paid` сейчас привязан к текущей бизнес-логике `UploadReceiptView`, где в `PAID` переводится payment после загрузки receipt.

---

## 19. Что полезно сделать на фронте дополнительно

Рекомендуется:

- добавить авто-reconnect для websocket
- добавить backoff: 1s → 2s → 5s → 10s
- при reconnect сразу делать `GET /api/v1/notifications/unread-count/`, если нужна быстрая сверка
- при заходе на экран уведомлений делать `GET /api/v1/notifications/`
- локально хранить `lastSeenNotificationId` или просто дедупить по `id`

---

## 20. Короткая памятка для фронтенда

### Подключение

```text
wss://<host>/ws/notifications/?token=<access_token>
```

### Что приходит первым

```json
{ "type": "notifications_snapshot", ... }
```

### Основные realtime-события

- `notification_created`
- `notification_read`
- `notifications_read_all`
- `pong`
- `error`

### Что можно отправлять в сокет

- `ping`
- `mark_read`
- `mark_all_read`

### REST fallback

- `GET /api/v1/notifications/`
- `GET /api/v1/notifications/unread-count/`
- `PATCH /api/v1/notifications/mark-read/`
- `PATCH /api/v1/notifications/mark-all-read/`

### Для навигации использовать

- `event_type`
- `auction_id`
- `deal_id`
- `payment_id`
- `real_property_id`
- `data`

---

## 21. Резюме

Этот модуль даёт:

- постоянное хранение уведомлений
- realtime через персональный websocket канал пользователя
- безопасную интеграцию через `transaction.on_commit`
- полное покрытие твоего ТЗ по уведомлениям
- удобную схему для фронта: `snapshot + delta updates + REST fallback`

Если отдашь этот README фронтенду, ему должно быть достаточно информации, чтобы:

- подключить websocket
- получать уведомления в реальном времени
- строить badge/unread count
- открывать нужные экраны по notification payload
- корректно работать с read/unread состоянием
