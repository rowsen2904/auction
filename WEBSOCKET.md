
# WebSocket guide (Django Channels) — Live bidding for OPEN auctions

This project uses **Django Channels** (ASGI) + **Uvicorn** to provide real-time bidding for **OPEN** auctions.
**CLOSED** auctions can stay on HTTP.

---

## 1) What you get

✅ Live stream of bids for an auction
✅ Atomic bid placement (race-safe)
✅ Broadcast updates to all connected clients in the same auction room
✅ JWT auth for websocket connections

---

## 2) WebSocket endpoint

> Recommended convention

- **WS URL**
  - Local (dev): `ws://localhost:8000/ws/auctions/<auction_id>/`
  - Prod (TLS): `wss://backend.migntender.app/ws/auctions/<auction_id>/`

Example:
- `wss://backend.migntender.app/ws/auctions/123/?token=<ACCESS_JWT>`

> Browsers cannot reliably send `Authorization` header during websocket handshake,
so the usual approach is passing JWT via querystring (`?token=`) or WS subprotocol.
This guide assumes querystring.

---

## 3) Auth flow (JWT)

1) Get access token (your existing HTTP auth)
2) Connect with:
   - `?token=<access_token>`

If token is invalid/expired:
- server should close connection with a policy error (e.g. close code `4401` or `4001`).

---

## 4) Message contract (client ↔ server)

All messages are JSON.

### 4.1 Client → Server

#### Place bid (OPEN auction)
```json
{
  "type": "bid.create",
  "amount": "2500.00"
}
````

Optional: include client-generated id for deduping (recommended)

```json
{
  "type": "bid.create",
  "amount": "2500.00",
  "client_id": "c0f0b9c2-0b91-4bfe-9b09-92c87cc2f4dd"
}
```

#### Ping (optional)

```json
{ "type": "ping" }
```

---

### 4.2 Server → Client

#### Bid created (broadcast to everyone in the auction room)

```json
{
  "type": "bid.created",
  "auction_id": 123,
  "bid": {
    "id": 55,
    "auction_id": 123,
    "broker_id": 999,
    "amount": "2500.00",
    "created_at": "2026-02-09T12:01:00Z"
  },
  "auction": {
    "id": 123,
    "property_id": 10,
    "owner_id": 1,
    "mode": "open",
    "min_price": "1000.00",
    "start_date": "2026-02-09T12:00:00Z",
    "end_date": "2026-02-09T14:00:00Z",
    "status": "active",
    "bids_count": 7,
    "current_price": "2500.00",
    "highest_bid_id": 55,
    "winner_bid_id": null,
    "created_at": "2026-02-01T10:00:00Z",
    "updated_at": "2026-02-09T12:01:00Z"
  }
}
```

#### Validation / business rule error (only to the sender)

```json
{
  "type": "error",
  "code": "AUCTION_NOT_ACTIVE",
  "detail": "Auction is not active."
}
```

Other typical codes:

* `NOT_AUTHENTICATED`
* `NOT_BROKER`
* `OWNER_CANNOT_BID`
* `BELOW_MIN_PRICE`
* `BID_NOT_HIGH_ENOUGH`
* `OUTSIDE_TIME_WINDOW`

#### Pong

```json
{ "type": "pong" }
```

---

## 5) Core business rules (server-side)

Bids are allowed only when:

1. `auction.status == ACTIVE`
2. `start_date <= now < end_date`
3. user is **Broker**
4. user is NOT the auction owner
5. `amount >= min_price`
6. For **OPEN** auctions:

   * `amount > current_price`

Also, bids must be race-safe:

* Use `transaction.atomic()`
* Use `select_for_update()` on the auction row

---

## 6) Room / group strategy

Each auction has its own broadcast group:

* Group name:

  * `auction_<auction_id>`

On connect:

* Add the socket to the group

On disconnect:

* Remove from group

On successful bid:

* `group_send()` a `bid.created` event to the group

---

## 7) Frontend usage (browser example)

### 7.1 Vanilla WebSocket

```js
const token = "<ACCESS_JWT>";
const auctionId = 123;

const ws = new WebSocket(`wss://backend.migntender.app/ws/auctions/${auctionId}/?token=${token}`);

ws.onopen = () => {
  console.log("connected");
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.type === "bid.created") {
    // Update UI (bids list, current price, bids_count, etc.)
    console.log("new bid:", msg.bid);
  }

  if (msg.type === "error") {
    console.error("bid error:", msg.code, msg.detail);
  }
};

ws.onclose = (e) => {
  console.log("closed", e.code, e.reason);
};

// Place bid
function placeBid(amount) {
  ws.send(JSON.stringify({ type: "bid.create", amount: String(amount) }));
}
```

### 7.2 Reconnect (recommended)

Implement reconnect with backoff (2s → 5s → 10s) and re-sync auction snapshot via HTTP if needed.

---

## 8) Testing with Insomnia (WebSocket)

Insomnia supports WebSocket requests.

1. Create **New Request → WebSocket**
2. URL:

   * `ws://localhost:8000/ws/auctions/123/?token=<ACCESS_JWT>`
3. Connect
4. Send message:

```json
{ "type": "bid.create", "amount": "2500.00" }
```

---

## 9) Running locally (Uvicorn + Redis)

### 9.1 Install

* `channels`
* `channels-redis`
* `uvicorn`

### 9.2 Django settings (Channel layer)

```py
# settings.py
import os

CHANNEL_LAYERS = {
  "default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {
      "hosts": [os.getenv("CHANNEL_REDIS_URL", "redis://127.0.0.1:6379/2")],
    },
  },
}
```

> Using a separate Redis DB index (like `/2`) is recommended.

### 9.3 `.env` example

```env
DJANGO_SETTINGS_MODULE=migtender.settings
CHANNEL_REDIS_URL=redis://127.0.0.1:6379/2
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

### 9.4 Start services

**Redis**

```bash
redis-server
```

**Uvicorn**

```bash
uvicorn migtender.asgi:application --host 0.0.0.0 --port 8000
```

**Celery worker**

```bash
celery -A migtender worker -l info
```

**Celery beat (for scheduled auction status)**

```bash
celery -A migtender beat -l info
```

---

## 10) Production notes (Nginx)

To support websockets, nginx must forward upgrade headers:

```nginx
location /ws/ {
  proxy_pass http://127.0.0.1:8000;
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_set_header Host $host;
  proxy_read_timeout 60s;
}
```

Use `wss://` in production (TLS).

---

## 11) Common issues & fixes

### 11.1 `Apps aren't loaded yet`

Fix imports order in `asgi.py`: **initialize Django first**, then import middleware/routing.

### 11.2 `1006` close code (abnormal close)

* wrong WS URL (`ws://` vs `wss://`)
* nginx missing upgrade headers
* middleware raises exception (check logs)

### 11.3 “Auction not active”

* status is not ACTIVE yet
* start_date not reached
* end_date passed
* celery/beat timezone mismatch → ensure consistent timezone settings

---

## 12) Recommended UI behavior (OPEN auctions)

* Show **current_price** (live)
* Show **bids_count** (live)
* Append a new bid to a live list (last 50)
* Highlight the current top bid
* Disable bidding button if:

  * auction not active
  * user not broker
  * user is owner
  * amount <= current_price
  * amount < min_price

---

## 13) Optional improvements

* Rate-limit bid.create (e.g. 3 requests/sec per socket)
* Deduplicate by `client_id`
* On connect, server can send initial snapshot:

  * `type: "auction.snapshot"` with latest auction + last N bids (open)
* Heartbeat ping/pong every 30s

---
