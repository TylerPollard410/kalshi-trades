# Usage Guide


- [Installation](#installation)
- [Quick Start](#quick-start)
  - [1. Configuration](#1-configuration)
  - [2. REST Client – Market Data (no auth
    required)](#2-rest-client--market-data-no-auth-required)
  - [3. REST Client – Authenticated
    Endpoints](#3-rest-client--authenticated-endpoints)
  - [4. Placing / Managing Orders](#4-placing--managing-orders)
  - [5. WebSocket Streaming](#5-websocket-streaming)
  - [6. Subscribing to Multiple
    Markets](#6-subscribing-to-multiple-markets)
  - [7. Private Channels (fills,
    positions)](#7-private-channels-fills-positions)
  - [8. Updating Subscriptions
    Dynamically](#8-updating-subscriptions-dynamically)
  - [9. Seeding OrderBook from REST before
    WebSocket](#9-seeding-orderbook-from-rest-before-websocket)
- [Strategy Loop](#strategy-loop)
  - [Running from the command line](#running-from-the-command-line)
  - [Using `Strategy` in a script or
    notebook](#using-strategy-in-a-script-or-notebook)
  - [Signal logic](#signal-logic)
- [CLI – Live Order Book Watcher](#cli--live-order-book-watcher)
- [CLI – Multi-Market Browser
  Dashboard](#cli--multi-market-browser-dashboard)
- [Historical Data](#historical-data)
- [Models Reference](#models-reference)

How to use the `kalshi_trades` package for REST queries, WebSocket
streaming, the live order-book CLI, and the multi-market browser
dashboard.

------------------------------------------------------------------------

## Installation

``` {bash}
#| label: install
# From the repo root (editable install)
uv pip install -e .

# With optional extras
uv pip install -e ".[viz,sdk]"
```

------------------------------------------------------------------------

## Quick Start

### 1. Configuration

The package reads credentials from environment variables (loaded from
`.env` or `.env.demo`):

    KALSHI_API_KEY_ID=your-api-key-id
    KALSHI_PRIVATE_KEY_PATH=/path/to/your/kalshi-key.key

``` python
from kalshi_trades import Config

# Demo environment (default)
config = Config(env="demo")
config
```

    Config(env='demo', env_file=None, private_key_path=None, rest_base='https://demo-api.kalshi.co/trade-api/v2', ws_url='wss://demo-api.kalshi.co/trade-api/ws/v2')

``` python
# Production
config = Config(env="prod")

# Explicit credentials (no .env needed)
config = Config(
    env="prod",
    api_key="your-key-id",
    private_key_path="/path/to/key.key",
)
```

### 2. REST Client – Market Data (no auth required)

``` python
from kalshi_trades import Config, KalshiClient

client = KalshiClient(Config(env="demo"))
```

#### Using a predefined ticker

``` python
# Find a BTC market with liquidity for examples
_btc = client.get_markets(series_ticker="KXBTC", status="open", limit=20)
_with_asks = [m for m in _btc["markets"] if float(m.get("yes_ask_size_fp", "0")) > 0]
EXAMPLE_TICKER = _with_asks[0]["ticker"] if _with_asks else _btc["markets"][0]["ticker"]
EXAMPLE_EVENT = _with_asks[0]["event_ticker"] if _with_asks else _btc["markets"][0]["event_ticker"]
EXAMPLE_SERIES = "KXBTC"
EXAMPLE_TICKER
```

    'KXBTC-26APR0501-T75799.99'

#### Single market detail

``` python
market = client.get_market(EXAMPLE_TICKER)
market
```

    {'market': {'can_close_early': True,
      'close_time': '2026-04-05T05:00:00Z',
      'created_time': '2026-04-04T13:48:29.536457Z',
      'event_ticker': 'KXBTC-26APR0501',
      'expected_expiration_time': '2026-04-05T05:05:00Z',
      'expiration_time': '2026-04-12T05:00:00Z',
      'expiration_value': '',
      'floor_strike': 75799.99,
      'fractional_trading_enabled': False,
      'last_price_dollars': '0.0000',
      'latest_expiration_time': '2026-04-12T05:00:00Z',
      'liquidity_dollars': '0.0000',
      'market_type': 'binary',
      'no_ask_dollars': '1.0000',
      'no_bid_dollars': '1.0000',
      'no_sub_title': '$75,800 or above',
      'notional_value_dollars': '1.0000',
      'open_interest_fp': '0.00',
      'open_time': '2026-04-04T14:09:20Z',
      'previous_price_dollars': '0.0000',
      'previous_yes_ask_dollars': '0.0000',
      'previous_yes_bid_dollars': '0.0000',
      'price_level_structure': 'linear_cent',
      'price_ranges': [{'end': '1.0000', 'start': '0.0000', 'step': '0.0100'}],
      'response_price_units': 'usd_cent',
      'result': '',
      'rules_primary': "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 1 AM EDT is above 75799.99 at 1 AM EDT on Apr 5, 2026, then the market resolves to Yes.",
      'rules_secondary': "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase may help guide your decision, the price used to determine this market is based on CF Benchmarks' corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices.",
      'settlement_timer_seconds': 60,
      'status': 'active',
      'strike_type': 'greater',
      'subtitle': '$75,800 or above',
      'tick_size': 1,
      'ticker': 'KXBTC-26APR0501-T75799.99',
      'title': 'Bitcoin price range  on Apr 5, 2026?',
      'updated_time': '2026-04-04T14:09:33.308789Z',
      'volume_24h_fp': '0.00',
      'volume_fp': '0.00',
      'yes_ask_dollars': '0.0000',
      'yes_ask_size_fp': '0.00',
      'yes_bid_dollars': '0.0000',
      'yes_bid_size_fp': '0.00',
      'yes_sub_title': '$75,800 or above'}}

#### List markets by series

``` python
# series_ticker is the top-level series (e.g. "KXBTC"), NOT the event ticker
data = client.get_markets(series_ticker=EXAMPLE_SERIES, status="open", limit=5)
[(m["ticker"], m["title"][:60]) for m in data["markets"]]
```

    [('KXBTC-26APR0501-T75799.99', 'Bitcoin price range  on Apr 5, 2026?'),
     ('KXBTC-26APR0501-T57200', 'Bitcoin price range  on Apr 5, 2026?'),
     ('KXBTC-26APR0501-B75750', 'Bitcoin price range  on Apr 5, 2026?'),
     ('KXBTC-26APR0501-B75650', 'Bitcoin price range  on Apr 5, 2026?'),
     ('KXBTC-26APR0501-B75550', 'Bitcoin price range  on Apr 5, 2026?')]

#### List markets by event

``` python
# event_ticker groups markets under one expiration window
data = client.get_markets(event_ticker=EXAMPLE_EVENT, status="open", limit=5)
[(m["ticker"], m["subtitle"][:60]) for m in data["markets"]]
```

    [('KXBTC-26APR0501-T75799.99', '$75,800 or above'),
     ('KXBTC-26APR0501-T57200', '$57,199.99 or below'),
     ('KXBTC-26APR0501-B75750', '$75,700 to 75,799.99'),
     ('KXBTC-26APR0501-B75650', '$75,600 to 75,699.99'),
     ('KXBTC-26APR0501-B75550', '$75,500 to 75,599.99')]

#### Auto-paginate through markets

``` python
import itertools

list(itertools.islice(
    client.paginate_markets(series_ticker=EXAMPLE_SERIES, status="open"), 5
))
```

    [{'can_close_early': True,
      'close_time': '2026-04-05T05:00:00Z',
      'created_time': '2026-04-04T13:48:29.536457Z',
      'event_ticker': 'KXBTC-26APR0501',
      'expected_expiration_time': '2026-04-05T05:05:00Z',
      'expiration_time': '2026-04-12T05:00:00Z',
      'expiration_value': '',
      'floor_strike': 75799.99,
      'fractional_trading_enabled': False,
      'last_price_dollars': '0.0000',
      'latest_expiration_time': '2026-04-12T05:00:00Z',
      'liquidity_dollars': '0.0000',
      'market_type': 'binary',
      'no_ask_dollars': '1.0000',
      'no_bid_dollars': '1.0000',
      'no_sub_title': '$75,800 or above',
      'notional_value_dollars': '1.0000',
      'open_interest_fp': '0.00',
      'open_time': '2026-04-04T14:09:20Z',
      'previous_price_dollars': '0.0000',
      'previous_yes_ask_dollars': '0.0000',
      'previous_yes_bid_dollars': '0.0000',
      'price_level_structure': 'linear_cent',
      'price_ranges': [{'end': '1.0000', 'start': '0.0000', 'step': '0.0100'}],
      'response_price_units': 'usd_cent',
      'result': '',
      'rules_primary': "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 1 AM EDT is above 75799.99 at 1 AM EDT on Apr 5, 2026, then the market resolves to Yes.",
      'rules_secondary': "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase may help guide your decision, the price used to determine this market is based on CF Benchmarks' corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices.",
      'settlement_timer_seconds': 60,
      'status': 'active',
      'strike_type': 'greater',
      'subtitle': '$75,800 or above',
      'tick_size': 1,
      'ticker': 'KXBTC-26APR0501-T75799.99',
      'title': 'Bitcoin price range  on Apr 5, 2026?',
      'updated_time': '2026-04-04T14:09:33.308789Z',
      'volume_24h_fp': '0.00',
      'volume_fp': '0.00',
      'yes_ask_dollars': '0.0000',
      'yes_ask_size_fp': '0.00',
      'yes_bid_dollars': '0.0000',
      'yes_bid_size_fp': '0.00',
      'yes_sub_title': '$75,800 or above'},
     {'can_close_early': True,
      'cap_strike': 57200,
      'close_time': '2026-04-05T05:00:00Z',
      'created_time': '2026-04-04T13:48:29.536457Z',
      'event_ticker': 'KXBTC-26APR0501',
      'expected_expiration_time': '2026-04-05T05:05:00Z',
      'expiration_time': '2026-04-12T05:00:00Z',
      'expiration_value': '',
      'fractional_trading_enabled': False,
      'last_price_dollars': '0.0000',
      'latest_expiration_time': '2026-04-12T05:00:00Z',
      'liquidity_dollars': '0.0000',
      'market_type': 'binary',
      'no_ask_dollars': '1.0000',
      'no_bid_dollars': '1.0000',
      'no_sub_title': '$57,199.99 or below',
      'notional_value_dollars': '1.0000',
      'open_interest_fp': '0.00',
      'open_time': '2026-04-04T14:09:20Z',
      'previous_price_dollars': '0.0000',
      'previous_yes_ask_dollars': '0.0000',
      'previous_yes_bid_dollars': '0.0000',
      'price_level_structure': 'linear_cent',
      'price_ranges': [{'end': '1.0000', 'start': '0.0000', 'step': '0.0100'}],
      'response_price_units': 'usd_cent',
      'result': '',
      'rules_primary': "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 1 AM EDT is below 57200 at 1 AM EDT on Apr 5, 2026, then the market resolves to Yes.",
      'rules_secondary': "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase may help guide your decision, the price used to determine this market is based on CF Benchmarks' corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices.",
      'settlement_timer_seconds': 60,
      'status': 'active',
      'strike_type': 'less',
      'subtitle': '$57,199.99 or below',
      'tick_size': 1,
      'ticker': 'KXBTC-26APR0501-T57200',
      'title': 'Bitcoin price range  on Apr 5, 2026?',
      'updated_time': '2026-04-04T14:09:33.227203Z',
      'volume_24h_fp': '0.00',
      'volume_fp': '0.00',
      'yes_ask_dollars': '0.0000',
      'yes_ask_size_fp': '0.00',
      'yes_bid_dollars': '0.0000',
      'yes_bid_size_fp': '0.00',
      'yes_sub_title': '$57,199.99 or below'},
     {'can_close_early': True,
      'cap_strike': 75799.99,
      'close_time': '2026-04-05T05:00:00Z',
      'created_time': '2026-04-04T13:48:29.536457Z',
      'event_ticker': 'KXBTC-26APR0501',
      'expected_expiration_time': '2026-04-05T05:05:00Z',
      'expiration_time': '2026-04-12T05:00:00Z',
      'expiration_value': '',
      'floor_strike': 75700,
      'fractional_trading_enabled': False,
      'last_price_dollars': '0.0000',
      'latest_expiration_time': '2026-04-12T05:00:00Z',
      'liquidity_dollars': '0.0000',
      'market_type': 'binary',
      'no_ask_dollars': '1.0000',
      'no_bid_dollars': '1.0000',
      'no_sub_title': '$75,700 to 75,799.99',
      'notional_value_dollars': '1.0000',
      'open_interest_fp': '0.00',
      'open_time': '2026-04-04T14:09:20Z',
      'previous_price_dollars': '0.0000',
      'previous_yes_ask_dollars': '0.0000',
      'previous_yes_bid_dollars': '0.0000',
      'price_level_structure': 'linear_cent',
      'price_ranges': [{'end': '1.0000', 'start': '0.0000', 'step': '0.0100'}],
      'response_price_units': 'usd_cent',
      'result': '',
      'rules_primary': "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 1 AM EDT is between 75700-75799.99 at 1 AM EDT on Apr 5, 2026, then the market resolves to Yes.",
      'rules_secondary': "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase may help guide your decision, the price used to determine this market is based on CF Benchmarks' corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices.",
      'settlement_timer_seconds': 60,
      'status': 'active',
      'strike_type': 'between',
      'subtitle': '$75,700 to 75,799.99',
      'tick_size': 1,
      'ticker': 'KXBTC-26APR0501-B75750',
      'title': 'Bitcoin price range  on Apr 5, 2026?',
      'updated_time': '2026-04-04T14:09:33.308789Z',
      'volume_24h_fp': '0.00',
      'volume_fp': '0.00',
      'yes_ask_dollars': '0.0000',
      'yes_ask_size_fp': '0.00',
      'yes_bid_dollars': '0.0000',
      'yes_bid_size_fp': '0.00',
      'yes_sub_title': '$75,700 to 75,799.99'},
     {'can_close_early': True,
      'cap_strike': 75699.99,
      'close_time': '2026-04-05T05:00:00Z',
      'created_time': '2026-04-04T13:48:29.536457Z',
      'event_ticker': 'KXBTC-26APR0501',
      'expected_expiration_time': '2026-04-05T05:05:00Z',
      'expiration_time': '2026-04-12T05:00:00Z',
      'expiration_value': '',
      'floor_strike': 75600,
      'fractional_trading_enabled': False,
      'last_price_dollars': '0.0000',
      'latest_expiration_time': '2026-04-12T05:00:00Z',
      'liquidity_dollars': '0.0000',
      'market_type': 'binary',
      'no_ask_dollars': '1.0000',
      'no_bid_dollars': '1.0000',
      'no_sub_title': '$75,600 to 75,699.99',
      'notional_value_dollars': '1.0000',
      'open_interest_fp': '0.00',
      'open_time': '2026-04-04T14:09:20Z',
      'previous_price_dollars': '0.0000',
      'previous_yes_ask_dollars': '0.0000',
      'previous_yes_bid_dollars': '0.0000',
      'price_level_structure': 'linear_cent',
      'price_ranges': [{'end': '1.0000', 'start': '0.0000', 'step': '0.0100'}],
      'response_price_units': 'usd_cent',
      'result': '',
      'rules_primary': "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 1 AM EDT is between 75600-75699.99 at 1 AM EDT on Apr 5, 2026, then the market resolves to Yes.",
      'rules_secondary': "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase may help guide your decision, the price used to determine this market is based on CF Benchmarks' corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices.",
      'settlement_timer_seconds': 60,
      'status': 'active',
      'strike_type': 'between',
      'subtitle': '$75,600 to 75,699.99',
      'tick_size': 1,
      'ticker': 'KXBTC-26APR0501-B75650',
      'title': 'Bitcoin price range  on Apr 5, 2026?',
      'updated_time': '2026-04-04T14:09:33.308789Z',
      'volume_24h_fp': '0.00',
      'volume_fp': '0.00',
      'yes_ask_dollars': '0.0000',
      'yes_ask_size_fp': '0.00',
      'yes_bid_dollars': '0.0000',
      'yes_bid_size_fp': '0.00',
      'yes_sub_title': '$75,600 to 75,699.99'},
     {'can_close_early': True,
      'cap_strike': 75599.99,
      'close_time': '2026-04-05T05:00:00Z',
      'created_time': '2026-04-04T13:48:29.536457Z',
      'event_ticker': 'KXBTC-26APR0501',
      'expected_expiration_time': '2026-04-05T05:05:00Z',
      'expiration_time': '2026-04-12T05:00:00Z',
      'expiration_value': '',
      'floor_strike': 75500,
      'fractional_trading_enabled': False,
      'last_price_dollars': '0.0000',
      'latest_expiration_time': '2026-04-12T05:00:00Z',
      'liquidity_dollars': '0.0000',
      'market_type': 'binary',
      'no_ask_dollars': '1.0000',
      'no_bid_dollars': '1.0000',
      'no_sub_title': '$75,500 to 75,599.99',
      'notional_value_dollars': '1.0000',
      'open_interest_fp': '0.00',
      'open_time': '2026-04-04T14:09:20Z',
      'previous_price_dollars': '0.0000',
      'previous_yes_ask_dollars': '0.0000',
      'previous_yes_bid_dollars': '0.0000',
      'price_level_structure': 'linear_cent',
      'price_ranges': [{'end': '1.0000', 'start': '0.0000', 'step': '0.0100'}],
      'response_price_units': 'usd_cent',
      'result': '',
      'rules_primary': "If the simple average of the sixty seconds of CF Benchmarks' Bitcoin Real-Time Index (BRTI) before 1 AM EDT is between 75500-75599.99 at 1 AM EDT on Apr 5, 2026, then the market resolves to Yes.",
      'rules_secondary': "Not all cryptocurrency price data is the same. While checking a source like Google or Coinbase may help guide your decision, the price used to determine this market is based on CF Benchmarks' corresponding Real Time Index (RTI). At the last minute before expiration, 60 RTI prices are collected. The official and final value is the average of these prices.",
      'settlement_timer_seconds': 60,
      'status': 'active',
      'strike_type': 'between',
      'subtitle': '$75,500 to 75,599.99',
      'tick_size': 1,
      'ticker': 'KXBTC-26APR0501-B75550',
      'title': 'Bitcoin price range  on Apr 5, 2026?',
      'updated_time': '2026-04-04T14:09:33.308789Z',
      'volume_24h_fp': '0.00',
      'volume_fp': '0.00',
      'yes_ask_dollars': '0.0000',
      'yes_ask_size_fp': '0.00',
      'yes_bid_dollars': '0.0000',
      'yes_bid_size_fp': '0.00',
      'yes_sub_title': '$75,500 to 75,599.99'}]

#### Order book

``` python
ob = client.get_market_orderbook(EXAMPLE_TICKER, depth=5)
ob
```

    {'orderbook_fp': {'no_dollars': [], 'yes_dollars': []}}

### 3. REST Client – Authenticated Endpoints

``` python
from kalshi_trades.models import Balance, Position, Order

# Balance
bal_data = client.get_balance()
bal = Balance.from_api(bal_data)
f"${bal.balance_dollars:.2f} available"
```

    '$500.00 available'

``` python
# Positions (first 5)
positions = list(itertools.islice(client.paginate_positions(count_filter="position"), 5))
[Position.from_api(p).ticker for p in positions]
```

    []

``` python
# Orders (first 5)
orders = list(itertools.islice(client.paginate_orders(), 5))
[Order.from_api(o).order_id for o in orders]
```

    ['321cbb3e-4447-4a45-8e43-d0cea65d06ff']

### 4. Placing / Managing Orders

``` python
# Place a limit order: buy 1 YES at 5¢
result = client.create_order(
    ticker="SOME-MARKET-TICKER",
    action="buy",
    side="yes",
    count=1,
    order_type="limit",
    yes_price=5,
)
order_id = result["order"]["order_id"]
order_id
```

``` python
# Amend the order price
client.amend_order(order_id, price=6)

# Cancel the order
client.cancel_order(order_id)

# Cancel all orders for a market
client.batch_cancel_orders(market_ticker="SOME-MARKET-TICKER")
```

### 5. WebSocket Streaming

``` python
import asyncio
from kalshi_trades import Config, KalshiAuth, KalshiWebSocket, OrderBook

config = Config(env="demo")
auth = KalshiAuth(
    api_key=config.get_api_key(),
    key_path=config.get_private_key_path(),
)
book = OrderBook("SOME-MARKET-TICKER")

ws = KalshiWebSocket(config=config, auth=auth)

# Register handlers
ws.on("orderbook_snapshot", lambda data: book.apply_snapshot(data["msg"], seq=data.get("seq")))
ws.on("orderbook_delta", lambda data: book.apply_delta(data["msg"], seq=data.get("seq")))
ws.on("ticker", lambda data: book.update_ticker(data["msg"]))
ws.on("trade", lambda data: book.update_trade(data["msg"]))


async def on_connect(ws_client):
    await ws_client.subscribe(
        channels=["orderbook_delta", "ticker", "trade"],
        market_ticker="SOME-MARKET-TICKER",
    )


asyncio.run(ws.run_forever(subscribe_on_connect=on_connect))
```

### 6. Subscribing to Multiple Markets

``` python
async def on_connect(ws_client):
    # Subscribe to tickers for all markets (no market_ticker → all)
    await ws_client.subscribe(channels=["ticker"])

    # Subscribe to orderbook for specific markets
    await ws_client.subscribe(
        channels=["orderbook_delta"],
        market_tickers=["TICKER-A", "TICKER-B"],
    )
```

### 7. Private Channels (fills, positions)

``` python
ws.on("fill", lambda data: print("Fill:", data["msg"]))

async def on_connect(ws_client):
    await ws_client.subscribe(channels=["fill"])
```

### 8. Updating Subscriptions Dynamically

``` python
async def example(ws_client):
    # Initial subscribe returns a command ID; the "subscribed" response
    # contains the subscription ID (sid)
    await ws_client.subscribe(
        channels=["orderbook_delta"],
        market_tickers=["TICKER-A"],
    )

    # Later, add a market to the existing subscription
    sid = 1  # from the "subscribed" response
    await ws_client.update_subscription(
        sid,
        action="add_markets",
        market_tickers=["TICKER-B"],
    )

    # Remove a market
    await ws_client.update_subscription(
        sid,
        action="delete_markets",
        market_tickers=["TICKER-A"],
    )
```

### 9. Seeding OrderBook from REST before WebSocket

``` python
from kalshi_trades import OrderBook

rest_data = client.get_market_orderbook(EXAMPLE_TICKER)
book = OrderBook.from_rest(EXAMPLE_TICKER, rest_data)

# book.yes and book.no are now populated
(book.best_bid(), book.best_ask(), book.spread())
```

    (None, None, None)

------------------------------------------------------------------------

## Strategy Loop

`kalshi_trades/strategy.py` streams the order book via WebSocket and
acts on imbalance signals. Use it as a script **or** import the
`Strategy` class into your own notebook / script.

### Running from the command line

``` {bash}
#| label: strategy-cli
#| eval: false
# Test mode — prints signals, no real orders placed (default)
python -m kalshi_trades.strategy TICKER

# Production mode — places real orders (requires .env credentials)
python -m kalshi_trades.strategy TICKER --mode prod

# Demo environment
python -m kalshi_trades.strategy TICKER --mode test --env demo
```

### Using `Strategy` in a script or notebook

``` python
import asyncio
from kalshi_trades.strategy import Strategy

strategy = Strategy(
    ticker="SOME-MARKET-TICKER",
    mode="test",   # "prod" to place real orders
    env="prod",
)

# Streams until Ctrl-C; prints a status line every 10 book updates
asyncio.run(strategy.run())
```

### Signal logic

The strategy calls `evaluate()` after every WebSocket update:

| Signal      | Condition                                              |
|-------------|--------------------------------------------------------|
| **BUY YES** | position flat AND `imbalance > 0.25` AND `spread ≤ 6¢` |
| **EXIT**    | position held AND `imbalance < -0.15`                  |
| **HOLD**    | otherwise                                              |

`imbalance` is `(bid_depth - ask_depth) / total_depth` across the top of
book. In test mode, orders are simulated and printed. In prod mode,
`create_order()` is called and any resting orders are cancelled before
exiting.

------------------------------------------------------------------------

## CLI – Live Order Book Watcher

``` {bash}
#| label: cli-watcher
#| eval: false
# Demo environment (default)
python -m kalshi_trades TICKER

# Production
python -m kalshi_trades TICKER --env prod

# Customize display
python -m kalshi_trades TICKER --side no --depth 12 --wall-threshold 500

# Debug mode (raw JSON messages)
python -m kalshi_trades TICKER --debug

# Via installed entry point
kalshi-watch TICKER --env prod
```

------------------------------------------------------------------------

## CLI – Multi-Market Browser Dashboard

``` {bash}
#| label: cli-dashboard
#| eval: false
# Watch your current positions and resting orders
kalshi-view --env prod

# Watch specific markets
kalshi-view TICKER-A TICKER-B

# Force every card to start in YES-only mode
kalshi-view TICKER-A TICKER-B --side yes

# Production, custom depth, do not auto-open the browser
kalshi-view TICKER-A TICKER-B --env prod --depth 12 --no-open
```

The dashboard reuses the same `OrderBook` and `KalshiWebSocket` logic as
the terminal watcher, but serves a local page so multiple markets can be
watched at once. If no tickers are provided, it automatically watches
markets where your portfolio currently has a non-zero position, then
adds any tickers with resting orders.

Each card now supports independent `YES`, `NO`, and `BOTH` modes, with
`BOTH` as the default. The browser UI also persists local controls for:

- hiding and reordering watchers
- pinning a primary watcher
- sorting by `Edge`, `Spread`, or `Imbalance`
- compact scan mode
- alert chips for abrupt spread widening or wall shifts

The most useful per-card trading signals are:

- `Edge Vs Mid` – whether last trade is stretched away from the current
  book midpoint
- `Depth 5¢` – near-touch liquidity on your side versus the opposite
  side
- `Imbalance` – top-of-book resting pressure

Use `--no-open` when you want the dashboard to stay in Positron Viewer
instead of auto-opening the external browser.

------------------------------------------------------------------------

## Historical Data

``` python
# Check the cutoff timestamps
cutoff = client.get_historical_cutoff()
cutoff
```

    {'market_settled_ts': '2026-01-02T00:00:00Z',
     'orders_updated_ts': '2026-01-02T00:00:00Z',
     'trades_created_ts': '2026-01-02T00:00:00Z'}

``` python
# Fetch settled markets older than the cutoff
hist = client.get_historical_markets(limit=5)
[(m["ticker"], m["status"]) for m in hist["markets"]]
```

    [('KXEPLGOAL-26JAN01CRYFUL-FULTCASTA21-1', 'finalized'),
     ('KXEPLGOAL-26JAN01CRYFUL-CRYJCANVO23-1', 'finalized'),
     ('KXEPLGOAL-26JAN01CRYFUL-FULSLUKIC20-1', 'finalized'),
     ('KXEPLGOAL-26JAN01CRYFUL-FULSBERGE16-1', 'finalized'),
     ('KXEPLGOAL-26JAN01CRYFUL-FULRJIMEN7-2', 'finalized')]

------------------------------------------------------------------------

## Models Reference

| Model | Key Fields |
|----|----|
| `Market` | `ticker`, `title`, `status`, `yes_bid_dollars`, `yes_ask_dollars`, `volume_fp` |
| `Event` | `event_ticker`, `title`, `category`, `markets` (list of `Market`) |
| `Series` | `ticker`, `title`, `frequency`, `category` |
| `Balance` | `balance` (cents), `portfolio_value` (cents), `.balance_dollars` property |
| `Position` | `ticker`, `position_fp`, `market_exposure_dollars`, `realized_pnl_dollars` |
| `Order` | `order_id`, `client_order_id`, `ticker`, `action`, `side`, `type`, `status` |
| `Fill` | `fill_id`, `order_id`, `ticker`, `side`, `action`, `count_fp`, `yes_price_dollars` |
| `Trade` | `trade_id`, `ticker`, `yes_price_dollars`, `count_fp`, `taker_side` |

All models expose `from_api(dict)` and store the original dict in
`_raw`.
