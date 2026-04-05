"""Local order book maintained from WebSocket snapshots and deltas.

The Kalshi orderbook only returns **bids** (YES bids and NO bids).  Asks are
implied:  YES ask = $1.00 − best NO bid, and vice-versa.

This module carries over all analytics from the original ``order_book.py``
(spread, imbalance, wall detection, terminal display) and adds:
    - Strict sequence-number validation (gap raises ``SequenceGapError``).
    - ``from_rest()`` factory to seed the book from the REST ``orderbook_fp``
      response before switching to the WebSocket delta stream.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class SequenceGapError(Exception):
    """Raised when an orderbook_delta arrives with a non-consecutive seq."""


class OrderBook:
    """In-memory order book for a single Kalshi market.

    Attributes
    ----------
    market_ticker : str
    yes : dict[str, str]
        ``{price_dollars: quantity_fp}`` for YES bids.
    no : dict[str, str]
        ``{price_dollars: quantity_fp}`` for NO bids.
    """

    def __init__(self, market_ticker: str) -> None:
        self.market_ticker = market_ticker

        # Price levels: {price_dollars_str: qty_fp_str}
        self.yes: dict[str, str] = {}
        self.no: dict[str, str] = {}
        self.last_seq: int | None = None
        self.last_event: str = "waiting"

        # Ticker fields
        self.ticker_price: Decimal | None = None
        self.ticker_yes_bid: Decimal | None = None
        self.ticker_yes_ask: Decimal | None = None
        self.volume_fp: str | None = None
        self.open_interest_fp: str | None = None

        # Last trade fields
        self.last_trade_yes_price: Decimal | None = None
        self.last_trade_no_price: Decimal | None = None
        self.last_trade_count_fp: str | None = None
        self.last_trade_side: str | None = None
        self.last_trade_ts: int | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    @staticmethod
    def _fmt_price(price: Decimal | None) -> str:
        if price is None:
            return "--"
        cents = int((price * 100).quantize(Decimal("1")))
        return f"{cents}¢"

    @staticmethod
    def _sorted_levels(levels: dict[str, str]) -> list[tuple[str, str]]:
        return sorted(levels.items(), key=lambda kv: Decimal(kv[0]), reverse=True)

    @staticmethod
    def _fmt_qty(qty: Any) -> str:
        if qty in (None, ""):
            return "--"
        return f"{Decimal(str(qty)):,.2f}"

    @staticmethod
    def _fmt_signed_price(price: Decimal | None) -> str:
        if price is None:
            return "--"
        cents = int((price * 100).quantize(Decimal("1")))
        sign = "+" if cents > 0 else ""
        return f"{sign}{cents}¢"

    # ------------------------------------------------------------------
    # Sequence tracking
    # ------------------------------------------------------------------
    def _set_seq(self, seq: int | None, msg_type: str) -> None:
        if seq is None:
            return
        if (
            self.last_seq is not None
            and msg_type == "orderbook_delta"
            and seq != self.last_seq + 1
        ):
            raise SequenceGapError(
                f"Sequence gap for {self.market_ticker}: "
                f"expected {self.last_seq + 1}, got {seq}"
            )
        self.last_seq = seq

    # ------------------------------------------------------------------
    # State updates
    # ------------------------------------------------------------------
    @classmethod
    def from_rest(cls, market_ticker: str, orderbook_data: dict[str, Any]) -> OrderBook:
        """Seed an ``OrderBook`` from the REST ``GET /markets/{ticker}/orderbook`` response.

        The REST response wraps levels inside ``orderbook_fp``.
        """
        ob = cls(market_ticker)
        fp = orderbook_data.get("orderbook_fp", orderbook_data)
        yes_levels = fp.get("yes_dollars", [])
        no_levels = fp.get("no_dollars", [])
        ob.yes = {price: qty for price, qty in yes_levels}
        ob.no = {price: qty for price, qty in no_levels}
        ob.last_event = "rest_snapshot"
        return ob

    def apply_snapshot(self, msg: dict[str, Any], seq: int | None = None) -> None:
        """Replace the entire book from a WebSocket ``orderbook_snapshot``."""
        yes_levels = (
            msg.get("yes_dollars_fp")
            or msg.get("yes_dollars")
            or msg.get("yes")
            or []
        )
        no_levels = (
            msg.get("no_dollars_fp")
            or msg.get("no_dollars")
            or msg.get("no")
            or []
        )
        self.yes = {price: qty for price, qty in yes_levels}
        self.no = {price: qty for price, qty in no_levels}
        self.last_event = "snapshot"
        self._set_seq(seq, "orderbook_snapshot")

    def apply_delta(self, msg: dict[str, Any], seq: int | None = None) -> None:
        """Apply an incremental ``orderbook_delta``."""
        side_book = self.yes if msg["side"] == "yes" else self.no
        price = msg.get("price_dollars", msg.get("price"))
        delta = msg.get("delta_fp", msg.get("delta"))

        if price is None or delta is None:
            raise KeyError("Orderbook delta missing price or delta field")

        new_qty = Decimal(side_book.get(price, "0")) + Decimal(delta)
        if new_qty <= 0:
            side_book.pop(price, None)
        else:
            side_book[price] = str(new_qty)

        self.last_event = "delta"
        self._set_seq(seq, "orderbook_delta")

    def update_ticker(self, msg: dict[str, Any]) -> None:
        """Update ticker fields from a WS ``ticker`` message."""
        self.ticker_price = self._to_decimal(msg.get("price_dollars"))
        self.ticker_yes_bid = self._to_decimal(msg.get("yes_bid_dollars"))
        self.ticker_yes_ask = self._to_decimal(msg.get("yes_ask_dollars"))
        self.volume_fp = msg.get("volume_fp")
        self.open_interest_fp = msg.get("open_interest_fp")
        self.last_event = "ticker"

    def update_trade(self, msg: dict[str, Any]) -> None:
        """Update last-trade fields from a WS ``trade`` message."""
        self.last_trade_yes_price = self._to_decimal(msg.get("yes_price_dollars"))
        self.last_trade_no_price = self._to_decimal(msg.get("no_price_dollars"))
        self.last_trade_count_fp = msg.get("count_fp")
        self.last_trade_side = msg.get("taker_side")
        self.last_trade_ts = msg.get("ts")
        self.last_event = "trade"

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------
    def best_bid(self, side: str = "yes") -> Decimal | None:
        book = self.yes if side == "yes" else self.no
        if not book:
            return None
        return max(Decimal(p) for p in book)

    def best_ask(self, side: str = "yes") -> Decimal | None:
        """Implied ask: $1.00 − best bid on the *opposite* side."""
        other = self.no if side == "yes" else self.yes
        if not other:
            return None
        return Decimal("1.00") - max(Decimal(p) for p in other)

    def spread(self, side: str = "yes") -> Decimal | None:
        bid = self.best_bid(side)
        ask = self.best_ask(side)
        if bid is None or ask is None:
            return None
        return ask - bid

    def mid(self, side: str = "yes") -> Decimal | None:
        bid = self.best_bid(side)
        ask = self.best_ask(side)
        if bid is None or ask is None:
            return None
        return (bid + ask) / 2

    def ticker_bid(self, side: str = "yes") -> Decimal | None:
        if side == "yes":
            return self.ticker_yes_bid
        if self.ticker_yes_ask is None:
            return None
        return Decimal("1.00") - self.ticker_yes_ask

    def ticker_ask(self, side: str = "yes") -> Decimal | None:
        if side == "yes":
            return self.ticker_yes_ask
        if self.ticker_yes_bid is None:
            return None
        return Decimal("1.00") - self.ticker_yes_bid

    def ticker_last(self, side: str = "yes") -> Decimal | None:
        if side == "yes":
            return self.ticker_price
        if self.ticker_price is None:
            return None
        return Decimal("1.00") - self.ticker_price

    def trade_price(self, side: str = "yes") -> Decimal | None:
        return self.last_trade_yes_price if side == "yes" else self.last_trade_no_price

    def imbalance(self, side: str = "yes", levels: int = 5) -> Decimal | None:
        """Order-flow imbalance across the top *levels* on each side.

        Returns a value in [-1, 1] where positive means more resting
        quantity on the own-side (bullish for that side).
        """
        own = self.yes if side == "yes" else self.no
        other = self.no if side == "yes" else self.yes
        own_total = sum(Decimal(q) for _, q in self._sorted_levels(own)[:levels])
        other_total = sum(Decimal(q) for _, q in self._sorted_levels(other)[:levels])
        total = own_total + other_total
        if total == 0:
            return None
        return (own_total - other_total) / total

    def wall_candidates(
        self,
        side: str = "yes",
        threshold: str = "1000.00",
        depth: int = 8,
    ) -> tuple[list[tuple[Decimal, Decimal]], list[tuple[Decimal, Decimal]]]:
        """Find price levels with resting qty >= *threshold*.

        Returns ``(own_walls, other_walls)`` where each wall is
        ``(price, qty)``.
        """
        threshold_dec = Decimal(str(threshold))
        own = self.yes if side == "yes" else self.no
        other = self.no if side == "yes" else self.yes

        own_walls = [
            (Decimal(p), Decimal(q))
            for p, q in self._sorted_levels(own)[:depth]
            if Decimal(q) >= threshold_dec
        ]
        other_walls = [
            (Decimal(p), Decimal(q))
            for p, q in self._sorted_levels(other)[:depth]
            if Decimal(q) >= threshold_dec
        ]
        return own_walls, other_walls

    def depth_at(self, side: str = "yes", within: str = "0.05") -> Decimal:
        """Total quantity within *within* dollars of the best bid."""
        book = self.yes if side == "yes" else self.no
        if not book:
            return Decimal("0")
        best = max(Decimal(p) for p in book)
        window = Decimal(within)
        return sum(
            Decimal(q)
            for p, q in book.items()
            if best - Decimal(p) <= window
        )

    def to_view(
        self,
        side: str = "yes",
        depth: int = 8,
        wall_threshold: str | None = None,
    ) -> dict[str, Any]:
        """Build a structured view of the current book for terminal or UI rendering."""
        bid = self.best_bid(side)
        ask = self.best_ask(side)
        sprd = self.spread(side)
        mid = self.mid(side)
        imb = self.imbalance(side)
        ticker_last = self.ticker_last(side)
        edge_vs_mid = None
        if ticker_last is not None and mid is not None:
            edge_vs_mid = ticker_last - mid
        label = side.upper()
        other_side = "no" if side == "yes" else "yes"
        own_depth_5c = self.depth_at(side, within="0.05")
        other_depth_5c = self.depth_at(other_side, within="0.05")

        own_walls: list[tuple[Decimal, Decimal]] = []
        other_walls: list[tuple[Decimal, Decimal]] = []
        threshold_dec = Decimal(str(wall_threshold)) if wall_threshold is not None else None
        if threshold_dec is not None:
            own_walls, other_walls = self.wall_candidates(
                side=side,
                threshold=wall_threshold,
                depth=depth,
            )

        other = self.no if side == "yes" else self.yes
        other_sorted = self._sorted_levels(other)[:depth]
        asks: list[dict[str, Any]] = []
        for price, qty in reversed(other_sorted):
            qty_dec = Decimal(qty)
            asks.append({
                "price": self._fmt_price(Decimal("1.00") - Decimal(price)),
                "qty": self._fmt_qty(qty),
                "is_wall": threshold_dec is not None and qty_dec >= threshold_dec,
            })

        own = self.yes if side == "yes" else self.no
        own_sorted = self._sorted_levels(own)[:depth]
        bids: list[dict[str, Any]] = []
        for price, qty in own_sorted:
            qty_dec = Decimal(qty)
            bids.append({
                "price": self._fmt_price(Decimal(price)),
                "qty": self._fmt_qty(qty),
                "is_wall": threshold_dec is not None and qty_dec >= threshold_dec,
            })

        best_bid_wall = None
        if own_walls:
            best_bid_wall = (
                f"{self._fmt_price(own_walls[0][0])} x {self._fmt_qty(own_walls[0][1])}"
            )

        best_ask_wall = None
        if other_walls:
            best_ask_wall = (
                f"{self._fmt_price(Decimal('1.00') - other_walls[0][0])} x "
                f"{self._fmt_qty(other_walls[0][1])}"
            )

        return {
            "market_ticker": self.market_ticker,
            "side": side,
            "label": label,
            "last_event": self.last_event,
            "last_seq": self.last_seq,
            "book_bid": self._fmt_price(bid),
            "book_ask": self._fmt_price(ask),
            "spread": self._fmt_price(sprd),
            "mid": self._fmt_price(mid),
            "ticker_last": self._fmt_price(ticker_last),
            "ticker_bid": self._fmt_price(self.ticker_bid(side)),
            "ticker_ask": self._fmt_price(self.ticker_ask(side)),
            "edge_vs_mid": self._fmt_signed_price(edge_vs_mid),
            "volume": self.volume_fp or "--",
            "open_interest": self.open_interest_fp or "--",
            "imbalance": f"{imb:.3f}" if imb is not None else "--",
            "depth_5c_own": self._fmt_qty(own_depth_5c),
            "depth_5c_other": self._fmt_qty(other_depth_5c),
            "last_trade_price": self._fmt_price(self.trade_price(side)),
            "last_trade_count": self.last_trade_count_fp or "--",
            "last_trade_side": self.last_trade_side or "--",
            "wall_threshold": self._fmt_qty(wall_threshold) if wall_threshold is not None else None,
            "best_bid_wall": best_bid_wall,
            "best_ask_wall": best_ask_wall,
            "asks": asks,
            "bids": bids,
        }

    # ------------------------------------------------------------------
    # Terminal display
    # ------------------------------------------------------------------
    def display(
        self,
        side: str = "yes",
        depth: int = 8,
        wall_threshold: str | None = None,
    ) -> None:
        """Pretty-print the book to the terminal (clears screen)."""
        view = self.to_view(side=side, depth=depth, wall_threshold=wall_threshold)

        print("\033[2J\033[H", end="")
        print(f"  {view['market_ticker']}  [{view['label']}]")
        print(
            f"  Event: {view['last_event']:<8} "
            f"Seq: {view['last_seq'] if view['last_seq'] is not None else '--'}"
        )
        print(
            f"  Book Bid: {view['book_bid']}   "
            f"Book Ask: {view['book_ask']}   "
            f"Spread: {view['spread']}"
        )
        print(
            f"  Ticker Last: {view['ticker_last']}   "
            f"{view['label']} Bid/Ask: {view['ticker_bid']}/{view['ticker_ask']}"
        )
        print(
            f"  Volume: {view['volume']}   "
            f"Open Interest: {view['open_interest']}   "
            f"Imbalance: {view['imbalance']}"
        )
        print(
            f"  Last Trade: {view['last_trade_price']} x "
            f"{view['last_trade_count']} ({view['last_trade_side']})"
        )
        if view["wall_threshold"] is not None:
            print(
                f"  Wall Threshold: {view['wall_threshold']}   "
                f"Best {view['label']} Bid Wall: {view['best_bid_wall'] or '--'}   "
                f"Best {view['label']} Ask Wall: {view['best_ask_wall'] or '--'}"
            )
        print()

        print(f"  -- {view['label']} Asks --")
        for row in view["asks"]:
            marker = "  <WALL>" if row["is_wall"] else ""
            print(
                f"    {row['price']:>4}  {row['qty']:>10} contracts{marker}"
            )

        print(f"  {'-' * 36}")

        print(f"  -- {view['label']} Bids --")
        for row in view["bids"]:
            marker = "  <WALL>" if row["is_wall"] else ""
            print(
                f"    {row['price']:>4}  {row['qty']:>10} contracts{marker}"
            )
        print()
