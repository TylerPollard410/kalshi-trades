"""
kalshi_trades – A Python package for interacting with the Kalshi prediction
market API (REST + WebSocket).

Provides:
    - KalshiAuth: RSA-PSS request signing for REST and WebSocket connections.
    - KalshiClient: Synchronous REST client covering markets, events, series,
      portfolio, orders, positions, fills, trades, and candlesticks.
    - OrderBook: Local order book state maintained from WebSocket snapshots
      and deltas, with spread/imbalance/wall analytics.
    - KalshiWebSocket: Async WebSocket client for real-time streaming across
      all Kalshi channels.
    - dashboard: Local multi-market browser dashboard served via
      ``kalshi-view`` or ``python -m kalshi_trades.dashboard``.
    - Config: Environment-aware configuration (prod / demo).
"""

from kalshi_trades.config import Config
from kalshi_trades.auth import KalshiAuth
from kalshi_trades.client import KalshiClient
from kalshi_trades.orderbook import OrderBook
from kalshi_trades.websocket import KalshiWebSocket

__all__ = [
    "Config",
    "KalshiAuth",
    "KalshiClient",
    "OrderBook",
    "KalshiWebSocket",
]
