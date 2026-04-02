├── watcher.py       # CLI entry point (live order-book display)
└── strategy.py      # Imbalance-based strategy loop (script or import)
```Kalshi](https://kalshi.com) prediction-market REST API and WebSocket streaming.

[![Render USAGE](https://github.com/tylerpollard410/kalshi-trades/actions/workflows/render-usage.yml/badge.svg)](https://github.com/tylerpollard410/kalshi-trades/actions/workflows/render-usage.yml)

---

## Installation

```bash
# Editable install from repo root
uv pip install -e .

# With optional extras
uv pip install -e ".[viz,sdk]"
```

Requires Python ≥ 3.13.

---

## Credentials

Copy `.env.example` to `.env` (prod) or `.env.demo` (demo) and fill in your values:

```
KALSHI_API_KEY_ID=your-api-key-id
KALSHI_PRIVATE_KEY_PATH=/path/to/your/kalshi-key.key
```

---

## Quick Start

```python
from kalshi_trades import Config, KalshiClient

# No credentials needed for public market data
client = KalshiClient(Config(env="prod"))

# Browse markets
markets = client.get_markets(series_ticker="KXBTC", status="open", limit=5)
for m in markets["markets"]:
    print(m["ticker"], m["subtitle"])

# Single market detail
market = client.get_market("KXBTC-26MAR2106-T80199.99")

# Order book snapshot
orderbook = client.get_market_orderbook("KXBTC-26MAR2106-T80199.99")
```

Authenticated endpoints (balance, orders, positions) work the same way once
credentials are set:

```python
client = KalshiClient(Config(env="prod"))  # loads .env automatically

balance  = client.get_balance()
orders   = client.get_orders(status="resting")
positions = client.get_positions()
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [USAGE.md](USAGE.md) | Full usage guide — REST, WebSocket, pagination, CLI |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Package design and what changed from the original layout |

---

## CLI

```bash
# Live order-book watcher (streams via WebSocket)
kalshi-watch KXBTC-26MAR2106-T80199.99
```

---

## Package layout

```
kalshi_trades/
├── __init__.py      # Public API re-exports
├── __main__.py      # python -m kalshi_trades → watcher CLI
├── config.py        # Environment-aware configuration (prod / demo)
├── auth.py          # RSA-PSS request signing
├── client.py        # Synchronous REST client
├── models.py        # Typed dataclass models
├── orderbook.py     # Local order book state + analytics
├── websocket.py     # Async WebSocket client
└── watcher.py       # CLI entry point
```