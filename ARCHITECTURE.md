# Architecture

This document describes the design of the `kalshi_trades` package and what
changed from the original flat-file layout.

---

## Package layout

```
kalshi_trades/
├── __init__.py      # Public API re-exports
├── __main__.py      # `python -m kalshi_trades` → watcher CLI
├── config.py        # Environment-aware configuration (prod / demo)
├── auth.py          # RSA-PSS request signing (REST + WebSocket)
├── client.py        # Synchronous REST client (all API endpoints)
├── dashboard.py     # Local browser dashboard for multiple markets
├── models.py        # Typed dataclass models for API responses
├── orderbook.py     # Local order book state + analytics
├── websocket.py     # Async WebSocket client for real-time streaming
├── watcher.py       # CLI entry point for the live order-book viewer
└── strategy.py      # Imbalance-based strategy loop (script or import)
```

Supporting files at the repo root:

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, `[project.scripts]` entry point |
| `auth.py` | **Legacy** – original flat auth module (kept for reference) |
| `order_book.py` | **Legacy** – original flat order book module |
| `watcher.py` | **Legacy** – original flat watcher script |
| `march_analyzer.py` | Standalone March Madness analyzer (unchanged) |

---

## What changed and why

### 1. Config (`config.py`)

**Before:** Environment selection, `.env` loading, and URL constants were
scattered across `watcher.py` with inline `if/else` blocks.

**After:** A frozen `Config` dataclass centralizes everything:
- Loads the correct `.env` / `.env.demo` file automatically.
- Exposes `rest_base` and `ws_url` based on `env="prod"` or `env="demo"`.
- Resolves `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH` from the
  environment or from explicit constructor arguments.

### 2. Auth (`auth.py`)

**Before:** `auth.py` at the repo root only produced WebSocket headers.

**After:** `KalshiAuth` now produces headers for **any** HTTP method + path,
which the REST client uses.  The signing algorithm follows the Kalshi docs
exactly:

```
message = timestamp_ms + METHOD + path_without_query_params
signature = RSA-PSS(SHA-256, salt_length=DIGEST_LENGTH)
```

Query parameters are stripped before signing, as required by the Kalshi
authenticated-requests documentation.

### 3. REST Client (`client.py`)

**Before:** No REST client existed – all REST interactions were done through
`pykalshi` or ad-hoc `requests` calls.

**After:** `KalshiClient` is a full synchronous HTTP client covering every
documented endpoint group:

| Group | Endpoints |
|-------|-----------|
| **Markets** | `get_markets`, `get_market`, `get_market_orderbook`, `get_trades`, `get_market_candlesticks` |
| **Events** | `get_event`, `get_events` |
| **Series** | `get_series`, `get_series_list` |
| **Portfolio** | `get_balance`, `get_positions`, `get_fills`, `get_settlements`, `get_portfolio_history`, `get_total_resting_order_value` |
| **Orders** | `get_orders`, `get_order`, `create_order`, `amend_order`, `cancel_order`, `batch_cancel_orders` |
| **Historical** | `get_historical_cutoff`, `get_historical_markets`, `get_historical_market_candlesticks`, `get_historical_fills`, `get_historical_orders` |

All list endpoints have `paginate_*` generators that handle cursor-based
pagination automatically.

`create_order` auto-generates a `client_order_id` (UUID4) when none is
provided, ensuring idempotent deduplication per the Kalshi docs.

### 4. Models (`models.py`)

**Before:** Raw dicts everywhere.

**After:** Typed `dataclasses` with `__slots__` for every major API object:
`Market`, `Event`, `Series`, `Balance`, `Position`, `Order`, `Fill`, `Trade`.

Each model exposes a `from_api(data)` classmethod that maps the raw JSON dict
into a typed Python object while preserving the original dict in `_raw` for
fields not explicitly modeled.

### 5. Order Book (`orderbook.py`)

**Before:** `order_book.py` at the repo root.

**After:** Same analytics (spread, imbalance, wall detection, terminal
display) plus:

- **`SequenceGapError`** – a dedicated exception raised when an
  `orderbook_delta` arrives out of sequence, so calling code can handle gaps
  (e.g., re-subscribe or re-seed from REST).
- **`from_rest()` factory** – seeds the book from the REST
  `GET /markets/{ticker}/orderbook` response, so you can pre-populate state
  before switching to WebSocket deltas.
- **`mid()`** – midpoint price.
- **`depth_at()`** – total quantity within a price window of the best bid.

### 6. WebSocket (`websocket.py`)

**Before:** `watcher.py` manually managed `websockets.connect()`, a
`while True` receive loop, and exponential-backoff reconnect.

**After:** `KalshiWebSocket` encapsulates the full lifecycle:

- **Handler registration** via `ws.on("msg_type", callback)`.
- **Subscription management** – `subscribe()`, `unsubscribe()`,
  `update_subscription()` (add/remove markets), `list_subscriptions()`.
- **`run_forever()`** – auto-reconnect loop with exponential backoff.  Accepts
  an async `subscribe_on_connect` callback so subscriptions are re-issued
  after each reconnect.
- **No manual ping/pong** – the `websockets` library handles protocol-level
  keepalive automatically, as confirmed by Kalshi's docs.

All documented channels are catalogued in `PUBLIC_CHANNELS` and
`PRIVATE_CHANNELS` class attributes.

### 7. Watcher CLI (`kalshi_trades/watcher.py`)

**Before:** `watcher.py` at the repo root was a monolithic script combining
env setup, auth, WS connection, message parsing, and display logic.

**After:** A thin CLI that composes `Config`, `KalshiAuth`, `OrderBook`, and
`KalshiWebSocket`.  Adds `--env` flag so you can switch prod/demo from the
command line.

Can be run three ways:
```bash
python -m kalshi_trades TICKER
python -m kalshi_trades.watcher TICKER
kalshi-watch TICKER            # after pip install
```

### 8. Browser Dashboard (`kalshi_trades/dashboard.py`)

The dashboard layers a local HTTP page and browser-facing WebSocket server on
top of the same `OrderBook` + `KalshiWebSocket` primitives used by the CLI
watcher. Each market keeps its own in-memory `OrderBook`, and the browser UI
renders those books from structured `to_view()` payloads rather than terminal
print calls.

The current dashboard adds several pieces of local UI state on top of the
streaming layer:

- Per-card `YES` / `NO` / `BOTH` view modes, with `BOTH` as the default.
- Watchlist controls for hide/show, manual reordering, and pinning a primary
  watcher to the top.
- Sort modes (`manual`, `edge`, `spread`, `imbalance`) and compact scan mode.
- Lightweight alert chips when spreads widen abruptly or large walls shift.

`OrderBook.to_view()` now carries extra microstructure fields that the browser
can render without another backend round trip, including midpoint, edge versus
mid, and near-touch depth.

### 9. pyproject.toml

- Bumped version to `0.2.0`.
- Core dependencies trimmed to only what `kalshi_trades` needs:
  `cryptography`, `python-dotenv`, `requests`, `websockets`.
- Original extras (`plotly`, `pykalshi`, `nbformat`) moved to optional
  dependency groups (`viz`, `sdk`, `notebook`, `all`).
- `[project.scripts]` exposes `kalshi-watch`, `kalshi-view`, and
  `kalshi-strategy`.

---

## Design principles

1. **Separation of concerns** – auth, HTTP transport, WS transport, domain
   models, and analytics live in distinct modules.
2. **Docs-first** – every signing, pagination, and keepalive behavior matches
   the Kalshi documentation exactly.
3. **No manual ping/pong** – the `websockets` library handles it; the Kalshi
   docs explicitly say so.
4. **Idempotent orders** – `create_order` always populates
   `client_order_id`.
5. **Query-param stripping** – signatures never include query params, per the
   Kalshi auth docs.
6. **Backward compatible** – the original flat files (`auth.py`,
   `order_book.py`, `watcher.py`, `march_analyzer.py`) are untouched and
   still runnable.
