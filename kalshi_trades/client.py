"""Synchronous REST client for the Kalshi Trade API v2.

Covers every resource group documented at https://docs.kalshi.com/api-reference:
    - Markets (get, list, orderbook, trades, candlesticks)
    - Events  (get, list)
    - Series  (get, list)
    - Portfolio (balance, positions, fills, settlements, orders, order CRUD)
    - Historical (cutoff, markets, candlesticks, fills, orders)

All list endpoints expose automatic cursor-based pagination via the
``paginate_*`` helpers.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterator
from urllib.parse import urlencode, urlparse

import requests

from kalshi_trades.auth import KalshiAuth
from kalshi_trades.config import Config


class KalshiClient:
    """Synchronous HTTP client for the Kalshi REST API.

    Parameters
    ----------
    config : Config
        A :class:`Config` instance that specifies env, credentials, and URLs.
    auth : KalshiAuth | None
        Pre-built auth object.  If *None*, one is created from *config*.
    timeout : float
        Default request timeout in seconds.
    """

    def __init__(
        self,
        config: Config | None = None,
        auth: KalshiAuth | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._config = config or Config()
        self._auth = auth or KalshiAuth(
            api_key=self._config.get_api_key(),
            key_path=self._config.get_private_key_path(),
        )
        self._base = self._config.rest_base
        self._timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------
    def _url(self, path: str) -> str:
        """Build full URL from a relative endpoint path like ``/markets``."""
        return f"{self._base}{path}"

    def _signed_headers(self, method: str, path: str) -> dict[str, str]:
        """Return signed headers for *method* + *path*.

        The ``path`` argument must be the portion **after** the host, e.g.
        ``/trade-api/v2/portfolio/balance``.
        """
        full_path = urlparse(self._url(path)).path
        return self._auth.headers(method, full_path)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        url = self._url(path)

        # Build query-string aware path for signing
        if params:
            qs = urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                sign_path = f"{path}?{qs}"
                url = f"{url}?{qs}"
            else:
                sign_path = path
        else:
            sign_path = path

        headers = self._signed_headers(method, sign_path) if authenticated else {}
        resp = self._session.request(
            method,
            url,
            headers=headers,
            json=json_body,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # Convenience wrappers
    def get(self, path: str, *, params: dict | None = None, auth: bool = True) -> dict:
        return self._request("GET", path, params=params, authenticated=auth)

    def post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json_body=body)

    def put(self, path: str, body: dict) -> dict:
        return self._request("PUT", path, json_body=body)

    def delete(self, path: str) -> dict:
        return self._request("DELETE", path)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------
    def _paginate(
        self,
        path: str,
        *,
        collection_key: str,
        params: dict[str, Any] | None = None,
        auth: bool = True,
        limit: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Yield items from a cursor-paginated list endpoint."""
        params = dict(params or {})
        params["limit"] = limit
        cursor: str | None = None

        while True:
            if cursor:
                params["cursor"] = cursor
            data = self.get(path, params=params, auth=auth)
            items = data.get(collection_key, [])
            yield from items
            cursor = data.get("cursor")
            if not cursor:
                break

    # ===================================================================
    # MARKET ENDPOINTS
    # ===================================================================
    def get_markets(self, **filters: Any) -> dict:
        """``GET /markets`` – list markets with optional filters.

        Supported filters: ``limit``, ``cursor``, ``event_ticker``,
        ``series_ticker``, ``status``, ``tickers`` (comma-separated), etc.
        """
        return self.get("/markets", params=filters, auth=False)

    def paginate_markets(self, **filters: Any) -> Iterator[dict]:
        """Auto-paginate through all markets matching *filters*."""
        return self._paginate("/markets", collection_key="markets", params=filters, auth=False)

    def get_market(self, ticker: str) -> dict:
        """``GET /markets/{ticker}`` – single market detail."""
        return self.get(f"/markets/{ticker}", auth=False)

    def get_market_orderbook(self, ticker: str, depth: int = 0) -> dict:
        """``GET /markets/{ticker}/orderbook`` – current order book.

        Parameters
        ----------
        depth : int
            0 = all levels, 1-100 for specific depth.
        """
        params = {"depth": depth} if depth else None
        return self.get(f"/markets/{ticker}/orderbook", params=params, auth=False)

    def get_trades(self, **filters: Any) -> dict:
        """``GET /markets/trades`` – public trade history."""
        return self.get("/markets/trades", params=filters, auth=False)

    def paginate_trades(self, **filters: Any) -> Iterator[dict]:
        return self._paginate("/markets/trades", collection_key="trades", params=filters, auth=False)

    def get_market_candlesticks(self, ticker: str, **params: Any) -> dict:
        """``GET /markets/{ticker}/candlesticks``."""
        return self.get(f"/markets/{ticker}/candlesticks", params=params, auth=False)

    # ===================================================================
    # EVENT ENDPOINTS
    # ===================================================================
    def get_event(self, event_ticker: str, *, with_nested_markets: bool = False) -> dict:
        """``GET /events/{event_ticker}``."""
        params = {"with_nested_markets": str(with_nested_markets).lower()}
        return self.get(f"/events/{event_ticker}", params=params, auth=False)

    def get_events(self, **filters: Any) -> dict:
        """``GET /events``."""
        return self.get("/events", params=filters, auth=False)

    def paginate_events(self, **filters: Any) -> Iterator[dict]:
        return self._paginate("/events", collection_key="events", params=filters, auth=False)

    # ===================================================================
    # SERIES ENDPOINTS
    # ===================================================================
    def get_series(self, series_ticker: str, *, include_volume: bool = False) -> dict:
        """``GET /series/{series_ticker}``."""
        params = {"include_volume": str(include_volume).lower()}
        return self.get(f"/series/{series_ticker}", params=params, auth=False)

    def get_series_list(self, **filters: Any) -> dict:
        """``GET /series``."""
        return self.get("/series", params=filters, auth=False)

    # ===================================================================
    # PORTFOLIO ENDPOINTS (authenticated)
    # ===================================================================
    def get_balance(self, *, subaccount: int | None = None) -> dict:
        """``GET /portfolio/balance``."""
        params = {"subaccount": subaccount} if subaccount is not None else None
        return self.get("/portfolio/balance", params=params)

    def get_positions(self, **filters: Any) -> dict:
        """``GET /portfolio/positions``."""
        return self.get("/portfolio/positions", params=filters)

    def paginate_positions(self, **filters: Any) -> Iterator[dict]:
        return self._paginate(
            "/portfolio/positions",
            collection_key="market_positions",
            params=filters,
        )

    def get_fills(self, **filters: Any) -> dict:
        """``GET /portfolio/fills``."""
        return self.get("/portfolio/fills", params=filters)

    def paginate_fills(self, **filters: Any) -> Iterator[dict]:
        return self._paginate("/portfolio/fills", collection_key="fills", params=filters)

    def get_settlements(self, **filters: Any) -> dict:
        """``GET /portfolio/settlements``."""
        return self.get("/portfolio/settlements", params=filters)

    def get_portfolio_history(self, **filters: Any) -> dict:
        """``GET /portfolio/history``."""
        return self.get("/portfolio/history", params=filters)

    def get_total_resting_order_value(self) -> dict:
        """``GET /portfolio/resting_order_value``."""
        return self.get("/portfolio/resting_order_value")

    # ===================================================================
    # ORDER ENDPOINTS (authenticated)
    # ===================================================================
    def get_orders(self, **filters: Any) -> dict:
        """``GET /portfolio/orders``."""
        return self.get("/portfolio/orders", params=filters)

    def paginate_orders(self, **filters: Any) -> Iterator[dict]:
        return self._paginate("/portfolio/orders", collection_key="orders", params=filters)

    def get_order(self, order_id: str) -> dict:
        """``GET /portfolio/orders/{order_id}``."""
        return self.get(f"/portfolio/orders/{order_id}")

    def create_order(
        self,
        *,
        ticker: str,
        action: str,
        side: str,
        count: int,
        order_type: str = "limit",
        yes_price: int | None = None,
        no_price: int | None = None,
        client_order_id: str | None = None,
        expiration_ts: int | None = None,
        sell_position_floor: int | None = None,
        buy_max_cost: int | None = None,
    ) -> dict:
        """``POST /portfolio/orders`` – place a new order.

        Parameters
        ----------
        ticker : str
            Market ticker.
        action : str
            ``"buy"`` or ``"sell"``.
        side : str
            ``"yes"`` or ``"no"``.
        count : int
            Number of contracts.
        order_type : str
            ``"limit"`` or ``"market"``.
        yes_price : int | None
            Limit price in cents for YES side (1-99).
        no_price : int | None
            Limit price in cents for NO side (1-99).
        client_order_id : str | None
            UUID for idempotent deduplication.  Auto-generated when *None*.
        """
        body: dict[str, Any] = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": count,
            "type": order_type,
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price
        if expiration_ts is not None:
            body["expiration_ts"] = expiration_ts
        if sell_position_floor is not None:
            body["sell_position_floor"] = sell_position_floor
        if buy_max_cost is not None:
            body["buy_max_cost"] = buy_max_cost
        return self.post("/portfolio/orders", body)

    def amend_order(
        self,
        order_id: str,
        *,
        count: int | None = None,
        price: int | None = None,
    ) -> dict:
        """``PUT /portfolio/orders/{order_id}`` – amend price or quantity."""
        body: dict[str, Any] = {}
        if count is not None:
            body["count"] = count
        if price is not None:
            body["price"] = price
        return self.put(f"/portfolio/orders/{order_id}", body)

    def cancel_order(self, order_id: str) -> dict:
        """``DELETE /portfolio/orders/{order_id}``."""
        return self.delete(f"/portfolio/orders/{order_id}")

    def batch_cancel_orders(self, *, market_ticker: str | None = None) -> dict:
        """``DELETE /portfolio/orders`` – cancel all (optionally per market)."""
        body: dict[str, Any] = {}
        if market_ticker:
            body["market_ticker"] = market_ticker
        return self._request("DELETE", "/portfolio/orders", json_body=body)

    # ===================================================================
    # HISTORICAL ENDPOINTS
    # ===================================================================
    def get_historical_cutoff(self) -> dict:
        """``GET /historical/cutoff``."""
        return self.get("/historical/cutoff", auth=False)

    def get_historical_markets(self, **filters: Any) -> dict:
        """``GET /historical/markets``."""
        return self.get("/historical/markets", params=filters, auth=False)

    def get_historical_market_candlesticks(self, ticker: str, **params: Any) -> dict:
        """``GET /historical/markets/{ticker}/candlesticks``."""
        return self.get(f"/historical/markets/{ticker}/candlesticks", params=params, auth=False)

    def get_historical_fills(self, **filters: Any) -> dict:
        """``GET /historical/fills``."""
        return self.get("/historical/fills", params=filters)

    def get_historical_orders(self, **filters: Any) -> dict:
        """``GET /historical/orders``."""
        return self.get("/historical/orders", params=filters)
