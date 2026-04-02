"""Live strategy loop — stream the order book and act on signals.

Usage
-----
Test mode (no real orders):
    python -m kalshi_trades.strategy KXNBASPREAD-26APR01ATLORL-ATL18 --mode test

Prod mode (real orders, requires .env credentials):
    python -m kalshi_trades.strategy KXNBASPREAD-26APR01ATLORL-ATL18 --mode prod

Strategy
--------
- BUY YES  when imbalance > BUY_THRESHOLD  and spread is tight
- SELL/EXIT when imbalance < EXIT_THRESHOLD (momentum flipping)
- HOLD      otherwise
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from kalshi_trades.config import Config
from kalshi_trades.client import KalshiClient
from kalshi_trades.orderbook import OrderBook
from kalshi_trades.websocket import KalshiWebSocket

# -----------------------------------------------------------------------
# Strategy parameters — tweak these
# -----------------------------------------------------------------------
BUY_THRESHOLD = Decimal("0.25")    # imbalance > 0.25 → buy signal
EXIT_THRESHOLD = Decimal("-0.15")  # imbalance < -0.15 → exit signal
MAX_SPREAD = Decimal("0.06")       # only enter when spread <= 6c
CONTRACTS = 1                      # contracts per order


# -----------------------------------------------------------------------
# Position tracker
# -----------------------------------------------------------------------
@dataclass
class Position:
    side: str = "yes"
    contracts: int = 0
    order_ids: list[str] = field(default_factory=list)

    @property
    def is_flat(self) -> bool:
        return self.contracts == 0


# -----------------------------------------------------------------------
# Strategy engine
# -----------------------------------------------------------------------
class Strategy:
    def __init__(
        self,
        ticker: str,
        mode: Literal["test", "prod"],
        env: str = "prod",
    ) -> None:
        self.ticker = ticker
        self.mode = mode
        self.config = Config(env=env)
        self.client = KalshiClient(self.config)
        self.book = OrderBook(ticker)
        self.position = Position()
        self._update_count = 0

    # ------------------------------------------------------------------
    # Order helpers
    # ------------------------------------------------------------------
    def _buy(self) -> None:
        bid = self.book.best_bid("yes")
        if bid is None:
            return
        price_cents = int((bid * 100).quantize(Decimal("1")))
        order_id = str(uuid.uuid4())

        if self.mode == "test":
            print(
                f"[TEST]  BUY  YES  {CONTRACTS}x @ {price_cents}c  "
                f"(imbalance={self.book.imbalance():.3f}, spread={self.book.spread()})"
            )
            self.position.contracts += CONTRACTS
            self.position.order_ids.append(order_id)
            return

        resp = self.client.create_order(
            ticker=self.ticker,
            action="buy",
            side="yes",
            count=CONTRACTS,
            order_type="limit",
            yes_price=price_cents,
            client_order_id=order_id,
        )
        real_id = resp.get("order", {}).get("order_id", order_id)
        self.position.contracts += CONTRACTS
        self.position.order_ids.append(real_id)
        print(
            f"[PROD]  BUY  YES  {CONTRACTS}x @ {price_cents}c  "
            f"order_id={real_id}"
        )

    def _exit(self) -> None:
        if self.position.is_flat:
            return

        ask = self.book.best_ask("yes")
        if ask is None:
            return
        price_cents = int((ask * 100).quantize(Decimal("1")))

        if self.mode == "test":
            print(
                f"[TEST]  SELL YES  {self.position.contracts}x @ {price_cents}c  "
                f"(imbalance={self.book.imbalance():.3f})"
            )
            self.position.contracts = 0
            self.position.order_ids.clear()
            return

        # Cancel any resting limit orders first
        for oid in list(self.position.order_ids):
            try:
                self.client.cancel_order(oid)
            except Exception:
                pass

        resp = self.client.create_order(
            ticker=self.ticker,
            action="sell",
            side="yes",
            count=self.position.contracts,
            order_type="limit",
            yes_price=price_cents,
        )
        real_id = resp.get("order", {}).get("order_id", "?")
        print(
            f"[PROD]  SELL YES  {self.position.contracts}x @ {price_cents}c  "
            f"order_id={real_id}"
        )
        self.position.contracts = 0
        self.position.order_ids.clear()

    # ------------------------------------------------------------------
    # Signal evaluation (called on every book update)
    # ------------------------------------------------------------------
    def evaluate(self) -> None:
        self._update_count += 1
        imbalance = self.book.imbalance()
        spread = self.book.spread()
        mid = self.book.mid()

        if imbalance is None or spread is None or mid is None:
            return

        # Status line every 10 updates
        if self._update_count % 10 == 0:
            pos_str = f"position={self.position.contracts}" if not self.position.is_flat else "flat"
            print(
                f"[{'TEST' if self.mode == 'test' else 'PROD'}]  "
                f"mid={int(mid*100)}c  "
                f"spread={int(spread*100)}c  "
                f"imbalance={float(imbalance):+.3f}  "
                f"{pos_str}"
            )

        # Entry: flat + strong imbalance + tight spread
        if self.position.is_flat and imbalance > BUY_THRESHOLD and spread <= MAX_SPREAD:
            self._buy()

        # Exit: holding + momentum flipping against us
        elif not self.position.is_flat and imbalance < EXIT_THRESHOLD:
            self._exit()

    # ------------------------------------------------------------------
    # Main stream loop
    # ------------------------------------------------------------------
    async def run(self) -> None:
        mode_label = "TEST (no real orders)" if self.mode == "test" else "PROD (live orders!)"
        print(f"Starting strategy [{mode_label}] on {self.ticker}")
        print(f"  buy_threshold={BUY_THRESHOLD}  exit_threshold={EXIT_THRESHOLD}  max_spread={MAX_SPREAD}")

        ws = KalshiWebSocket(self.config)
        async for msg_type, msg in ws.stream(self.ticker):
            if msg_type == "orderbook_snapshot":
                self.book.apply_snapshot(msg)
            elif msg_type == "orderbook_delta":
                self.book.apply_delta(msg)
            elif msg_type == "ticker":
                self.book.update_ticker(msg)
            elif msg_type == "trade":
                self.book.update_trade(msg)
            self.evaluate()


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------
def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalshi live strategy")
    p.add_argument("ticker", help="Market ticker, e.g. KXNBASPREAD-26APR01ATLORL-ATL18")
    p.add_argument(
        "--mode",
        choices=["test", "prod"],
        default="test",
        help="test = print signals only, prod = place real orders (default: test)",
    )
    p.add_argument("--env", default="prod", help="Kalshi env: prod or demo (default: prod)")
    return p.parse_args()


def cli() -> None:
    args = _parse()
    strategy = Strategy(ticker=args.ticker, mode=args.mode, env=args.env)
    try:
        asyncio.run(strategy.run())
    except KeyboardInterrupt:
        print("\nStopped.")
        if not strategy.position.is_flat:
            print(f"WARNING: open position of {strategy.position.contracts} contracts -- exit manually!")


if __name__ == "__main__":
    cli()
