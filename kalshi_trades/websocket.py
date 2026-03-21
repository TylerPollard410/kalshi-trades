"""Async WebSocket client for Kalshi real-time streaming.

Handles all documented channels:
    Public  – ``ticker``, ``trade``, ``market_lifecycle_v2``, ``multivariate``
    Private – ``orderbook_delta``, ``fill``, ``market_positions``,
              ``communications``, ``order_group_updates``

The ``websockets`` library automatically handles protocol-level ping/pong
frames, so **no manual heartbeat** is needed (per Kalshi docs).

Connection lifecycle:
    1. Authenticate via headers during the WS handshake.
    2. Send ``subscribe`` commands for desired channels.
    3. Receive and route messages to user-supplied callbacks.
    4. On disconnect, reconnect with exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import websockets
from websockets.asyncio.client import ClientConnection

from kalshi_trades.auth import KalshiAuth
from kalshi_trades.config import Config

logger = logging.getLogger(__name__)

# Type alias for message callbacks
MessageHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class KalshiWebSocket:
    """Async WebSocket manager for Kalshi real-time data.

    Parameters
    ----------
    config : Config
        Environment configuration (contains WS URL).
    auth : KalshiAuth | None
        Pre-built auth.  Built from *config* when *None*.
    on_message : MessageHandler | None
        Default callback invoked for every received message.
    max_reconnect_delay : float
        Upper bound for exponential-backoff reconnect (seconds).
    """

    # All documented channels
    PUBLIC_CHANNELS = frozenset({
        "ticker",
        "trade",
        "market_lifecycle_v2",
        "multivariate",
    })
    PRIVATE_CHANNELS = frozenset({
        "orderbook_delta",
        "fill",
        "market_positions",
        "communications",
        "order_group_updates",
    })
    ALL_CHANNELS = PUBLIC_CHANNELS | PRIVATE_CHANNELS

    def __init__(
        self,
        config: Config | None = None,
        auth: KalshiAuth | None = None,
        on_message: MessageHandler | None = None,
        max_reconnect_delay: float = 30.0,
    ) -> None:
        self._config = config or Config()
        self._auth = auth or KalshiAuth(
            api_key=self._config.get_api_key(),
            key_path=self._config.get_private_key_path(),
        )
        self._ws_url = self._config.ws_url
        self._on_message = on_message
        self._max_reconnect_delay = max_reconnect_delay

        # Per-type callbacks: msg_type -> handler
        self._handlers: dict[str, MessageHandler] = {}

        # Subscription bookkeeping
        self._msg_id = 1
        self._subscriptions: dict[int, dict[str, Any]] = {}  # sid -> params

        # Connection state
        self._ws: ClientConnection | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------
    def on(self, msg_type: str, handler: MessageHandler) -> None:
        """Register *handler* for messages of *msg_type*.

        Example::

            ws.on("ticker", my_ticker_handler)
            ws.on("orderbook_snapshot", my_snapshot_handler)
            ws.on("orderbook_delta", my_delta_handler)
            ws.on("fill", my_fill_handler)
            ws.on("trade", my_trade_handler)
        """
        self._handlers[msg_type] = handler

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------
    async def subscribe(
        self,
        channels: list[str],
        *,
        market_ticker: str | None = None,
        market_tickers: list[str] | None = None,
    ) -> int:
        """Send a ``subscribe`` command and return the command ``id``.

        Parameters
        ----------
        channels : list[str]
            Channel names, e.g. ``["orderbook_delta", "ticker"]``.
        market_ticker : str | None
            Single market ticker (for channels that require one).
        market_tickers : list[str] | None
            Multiple market tickers.
        """
        params: dict[str, Any] = {"channels": channels}
        if market_ticker:
            params["market_ticker"] = market_ticker
        if market_tickers:
            params["market_tickers"] = market_tickers

        cmd_id = self._msg_id
        self._msg_id += 1
        await self._send({"id": cmd_id, "cmd": "subscribe", "params": params})
        return cmd_id

    async def unsubscribe(self, sids: list[int]) -> int:
        """Send an ``unsubscribe`` command for the given subscription IDs."""
        cmd_id = self._msg_id
        self._msg_id += 1
        await self._send({"id": cmd_id, "cmd": "unsubscribe", "params": {"sids": sids}})
        return cmd_id

    async def update_subscription(
        self,
        sid: int,
        *,
        action: str,
        market_tickers: list[str],
    ) -> int:
        """Send ``update_subscription`` to add/remove markets from *sid*.

        Parameters
        ----------
        sid : int
            Subscription ID returned in the ``subscribed`` response.
        action : str
            ``"add_markets"`` or ``"delete_markets"``.
        market_tickers : list[str]
            Tickers to add or remove.
        """
        cmd_id = self._msg_id
        self._msg_id += 1
        await self._send({
            "id": cmd_id,
            "cmd": "update_subscription",
            "params": {
                "sids": [sid],
                "action": action,
                "market_tickers": market_tickers,
            },
        })
        return cmd_id

    async def list_subscriptions(self) -> int:
        """Send ``list_subscriptions`` command."""
        cmd_id = self._msg_id
        self._msg_id += 1
        await self._send({"id": cmd_id, "cmd": "list_subscriptions"})
        return cmd_id

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> None:
        """Open the WebSocket connection (no reconnect loop)."""
        headers = self._auth.ws_headers()
        self._ws = await websockets.connect(
            self._ws_url,
            additional_headers=headers,
        )
        logger.info("Connected to %s", self._ws_url)

    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def listen(self) -> None:
        """Block and process incoming messages until disconnected."""
        if self._ws is None:
            raise RuntimeError("Not connected. Call connect() first.")
        self._running = True
        async for raw in self._ws:
            data = json.loads(raw)
            await self._dispatch(data)

    async def run_forever(
        self,
        subscribe_on_connect: Callable[..., Awaitable[None]] | None = None,
    ) -> None:
        """Connect, subscribe, listen — reconnecting on failures.

        Parameters
        ----------
        subscribe_on_connect : callable | None
            Async function called after each (re)connect so you can
            re-issue your subscribe commands.  Receives ``self`` as the
            sole argument.
        """
        backoff = 1.0
        self._running = True

        while self._running:
            try:
                await self.connect()
                if subscribe_on_connect:
                    await subscribe_on_connect(self)
                backoff = 1.0
                await self.listen()
            except KeyboardInterrupt:
                break
            except websockets.exceptions.InvalidStatus as exc:
                logger.error("Handshake failed: %s", exc)
                raise
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    "Disconnected (%s: %s). Reconnecting in %.0fs…",
                    type(exc).__name__,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_reconnect_delay)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected.")
        raw = json.dumps(payload)
        logger.debug("→ %s", raw)
        await self._ws.send(raw)

    async def _dispatch(self, data: dict[str, Any]) -> None:
        msg_type = data.get("type", "")
        logger.debug("← %s", msg_type)

        # Route to per-type handler
        handler = self._handlers.get(msg_type)
        if handler:
            result = handler(data)
            if asyncio.iscoroutine(result):
                await result

        # Also invoke the catch-all handler
        if self._on_message:
            result = self._on_message(data)
            if asyncio.iscoroutine(result):
                await result
