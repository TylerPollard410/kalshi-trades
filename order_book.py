from decimal import Decimal


class OrderBook:
    def __init__(self, market_ticker):
        self.market_ticker = market_ticker
        self.yes = {}  # price_dollars -> quantity_fp
        self.no = {}

    def apply_snapshot(self, msg):
        yes_levels = msg.get("yes_dollars", msg.get("yes", []))
        no_levels = msg.get("no_dollars", msg.get("no", []))
        self.yes = {price: qty for price, qty in yes_levels}
        self.no = {price: qty for price, qty in no_levels}

    def apply_delta(self, msg):
        side = self.yes if msg["side"] == "yes" else self.no
        price = msg.get("price_dollars", msg.get("price"))
        delta = msg.get("delta_fp", msg.get("delta"))

        if price is None or delta is None:
            raise KeyError("Orderbook delta missing price or delta field")

        new_qty = Decimal(side.get(price, "0")) + Decimal(delta)
        if new_qty <= 0:
            side.pop(price, None)
        else:
            side[price] = str(new_qty)

    def best_bid(self, side="yes"):
        book = self.yes if side == "yes" else self.no
        if not book:
            return None
        return max(Decimal(price) for price in book)

    def best_ask(self, side="yes"):
        other = self.no if side == "yes" else self.yes
        if not other:
            return None
        return Decimal("1.00") - max(Decimal(price) for price in other)

    def spread(self, side="yes"):
        bid = self.best_bid(side)
        ask = self.best_ask(side)
        if bid is None or ask is None:
            return None
        return ask - bid

    @staticmethod
    def _fmt_price(price):
        if price is None:
            return "--"
        cents = int((price * 100).quantize(Decimal("1")))
        return f"{cents}c"

    @staticmethod
    def _sorted_levels(levels):
        return sorted(levels.items(), key=lambda item: Decimal(item[0]), reverse=True)

    def display(self, side="yes"):
        bid = self.best_bid(side)
        ask = self.best_ask(side)
        spread = self.spread(side)
        label = side.upper()

        print("\033[2J\033[H", end="")
        print(f"  {self.market_ticker}  [{label}]")
        print(
            f"  Best Bid: {self._fmt_price(bid)}   "
            f"Best Ask: {self._fmt_price(ask)}   "
            f"Spread: {self._fmt_price(spread)}"
        )
        print()

        other = self.no if side == "yes" else self.yes
        other_sorted = self._sorted_levels(other)[:8]
        print(f"  -- {label} Asks --")
        for price, qty in reversed(other_sorted):
            ask_price = Decimal("1.00") - Decimal(price)
            print(f"    {self._fmt_price(ask_price):>4}  {qty:>8} contracts")

        print(f"  {'-' * 32}")

        own = self.yes if side == "yes" else self.no
        own_sorted = self._sorted_levels(own)[:8]
        print(f"  -- {label} Bids --")
        for price, qty in own_sorted:
            print(f"    {self._fmt_price(Decimal(price)):>4}  {qty:>8} contracts")

        print()
