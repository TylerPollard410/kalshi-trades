"""Typed data models for Kalshi API responses.

All models use ``dataclasses`` with ``__slots__`` for low overhead.  Every
model exposes a ``from_api(data)`` classmethod that builds an instance from
the raw JSON dict returned by the REST API or WebSocket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string or return *None*."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Market / Event / Series
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Market:
    ticker: str
    event_ticker: str
    title: str
    subtitle: str | None = None
    market_type: str = "binary"
    status: str = "open"
    yes_bid_dollars: str | None = None
    yes_ask_dollars: str | None = None
    no_bid_dollars: str | None = None
    no_ask_dollars: str | None = None
    last_price_dollars: str | None = None
    volume_fp: str | None = None
    volume_24h_fp: str | None = None
    open_interest_fp: str | None = None
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    result: str | None = None
    created_time: datetime | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    expiration_time: datetime | None = None
    settlement_ts: datetime | None = None
    can_close_early: bool = False
    tick_size: int | None = None
    rules_primary: str | None = None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Market:
        return cls(
            ticker=data["ticker"],
            event_ticker=data.get("event_ticker", ""),
            title=data.get("title", ""),
            subtitle=data.get("subtitle"),
            market_type=data.get("market_type", "binary"),
            status=data.get("status", ""),
            yes_bid_dollars=data.get("yes_bid_dollars"),
            yes_ask_dollars=data.get("yes_ask_dollars"),
            no_bid_dollars=data.get("no_bid_dollars"),
            no_ask_dollars=data.get("no_ask_dollars"),
            last_price_dollars=data.get("last_price_dollars"),
            volume_fp=data.get("volume_fp"),
            volume_24h_fp=data.get("volume_24h_fp"),
            open_interest_fp=data.get("open_interest_fp"),
            yes_sub_title=data.get("yes_sub_title"),
            no_sub_title=data.get("no_sub_title"),
            result=data.get("result"),
            created_time=_ts(data.get("created_time")),
            open_time=_ts(data.get("open_time")),
            close_time=_ts(data.get("close_time")),
            expiration_time=_ts(data.get("expiration_time")),
            settlement_ts=_ts(data.get("settlement_ts")),
            can_close_early=data.get("can_close_early", False),
            tick_size=data.get("tick_size"),
            rules_primary=data.get("rules_primary"),
            _raw=data,
        )


@dataclass(slots=True)
class Event:
    event_ticker: str
    series_ticker: str
    title: str
    subtitle: str | None = None
    category: str | None = None
    mutually_exclusive: bool = True
    markets: list[Market] = field(default_factory=list)
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Event:
        markets = [Market.from_api(m) for m in data.get("markets", [])]
        return cls(
            event_ticker=data["event_ticker"],
            series_ticker=data.get("series_ticker", ""),
            title=data.get("title", ""),
            subtitle=data.get("sub_title"),
            category=data.get("category"),
            mutually_exclusive=data.get("mutually_exclusive", True),
            markets=markets,
            _raw=data,
        )


@dataclass(slots=True)
class Series:
    ticker: str
    title: str
    frequency: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    volume_fp: str | None = None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Series:
        return cls(
            ticker=data["ticker"],
            title=data.get("title", ""),
            frequency=data.get("frequency"),
            category=data.get("category"),
            tags=data.get("tags", []),
            volume_fp=data.get("volume_fp"),
            _raw=data,
        )


# ---------------------------------------------------------------------------
# Portfolio models
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class Balance:
    balance: int
    portfolio_value: int
    updated_ts: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Balance:
        return cls(
            balance=data["balance"],
            portfolio_value=data["portfolio_value"],
            updated_ts=data["updated_ts"],
        )

    @property
    def balance_dollars(self) -> float:
        return self.balance / 100

    @property
    def portfolio_value_dollars(self) -> float:
        return self.portfolio_value / 100


@dataclass(slots=True)
class Position:
    ticker: str
    position_fp: str
    market_exposure_dollars: str | None = None
    realized_pnl_dollars: str | None = None
    total_traded_dollars: str | None = None
    resting_orders_count: int = 0
    fees_paid_dollars: str | None = None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Position:
        return cls(
            ticker=data["ticker"],
            position_fp=data.get("position_fp", "0"),
            market_exposure_dollars=data.get("market_exposure_dollars"),
            realized_pnl_dollars=data.get("realized_pnl_dollars"),
            total_traded_dollars=data.get("total_traded_dollars"),
            resting_orders_count=data.get("resting_orders_count", 0),
            fees_paid_dollars=data.get("fees_paid_dollars"),
            _raw=data,
        )


@dataclass(slots=True)
class Order:
    order_id: str
    ticker: str
    client_order_id: str
    action: str
    side: str
    type: str
    status: str
    count: int = 0
    yes_price: int | None = None
    no_price: int | None = None
    created_time: datetime | None = None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Order:
        return cls(
            order_id=data.get("order_id", ""),
            ticker=data.get("ticker", ""),
            client_order_id=data.get("client_order_id", ""),
            action=data.get("action", ""),
            side=data.get("side", ""),
            type=data.get("type", ""),
            status=data.get("status", ""),
            count=data.get("count", 0),
            yes_price=data.get("yes_price"),
            no_price=data.get("no_price"),
            created_time=_ts(data.get("created_time")),
            _raw=data,
        )


@dataclass(slots=True)
class Fill:
    fill_id: str
    trade_id: str
    order_id: str
    ticker: str
    side: str
    action: str
    count_fp: str
    yes_price_dollars: str | None = None
    no_price_dollars: str | None = None
    is_taker: bool = False
    fee_cost: str | None = None
    client_order_id: str | None = None
    created_time: datetime | None = None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Fill:
        return cls(
            fill_id=data.get("fill_id", ""),
            trade_id=data.get("trade_id", ""),
            order_id=data.get("order_id", ""),
            ticker=data.get("ticker", data.get("market_ticker", "")),
            side=data.get("side", ""),
            action=data.get("action", ""),
            count_fp=data.get("count_fp", "0"),
            yes_price_dollars=data.get("yes_price_dollars"),
            no_price_dollars=data.get("no_price_dollars"),
            is_taker=data.get("is_taker", False),
            fee_cost=data.get("fee_cost"),
            client_order_id=data.get("client_order_id"),
            created_time=_ts(data.get("created_time")),
            _raw=data,
        )


@dataclass(slots=True)
class Trade:
    """A public trade from the ``/markets/trades`` endpoint or WS ``trade`` channel."""
    trade_id: str | None = None
    ticker: str | None = None
    yes_price_dollars: str | None = None
    no_price_dollars: str | None = None
    count_fp: str | None = None
    taker_side: str | None = None
    ts: int | None = None
    created_time: datetime | None = None
    _raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Trade:
        return cls(
            trade_id=data.get("trade_id"),
            ticker=data.get("ticker", data.get("market_ticker")),
            yes_price_dollars=data.get("yes_price_dollars"),
            no_price_dollars=data.get("no_price_dollars"),
            count_fp=data.get("count_fp"),
            taker_side=data.get("taker_side"),
            ts=data.get("ts"),
            created_time=_ts(data.get("created_time")),
            _raw=data,
        )
