#!/usr/bin/env python3
"""
Local backtester for round 4 CSVs. No external prosperity4bt dependency.

Usage (from project root):
    python3 backtesting/local_backtest.py round4/algo/get_mark38_test.py
    python3 backtesting/local_backtest.py round4/algo/get_mark38_test.py --days 1 2
    python3 backtesting/local_backtest.py round4/algo/get_mark38_test.py --merge-pnl
"""

import sys
import csv
import json
import argparse
import importlib.util
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Minimal datamodel (no jsonpickle dependency)
# ---------------------------------------------------------------------------

class Listing:
    def __init__(self, symbol, product, denomination):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination

class OrderDepth:
    def __init__(self):
        self.buy_orders = {}   # {price: qty}  qty > 0
        self.sell_orders = {}  # {price: qty}  qty < 0

class Order:
    def __init__(self, symbol, price, quantity):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
    def __repr__(self):
        return f"({self.symbol}, {self.price}, {self.quantity})"

class Trade:
    def __init__(self, symbol, price, quantity, buyer=None, seller=None, timestamp=0):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

class ConversionObservation:
    def __init__(self, bidPrice=0, askPrice=0, transportFees=0,
                 exportTariff=0, importTariff=0, sugarPrice=0, sunlightIndex=0):
        self.bidPrice = bidPrice
        self.askPrice = askPrice
        self.transportFees = transportFees
        self.exportTariff = exportTariff
        self.importTariff = importTariff
        self.sugarPrice = sugarPrice
        self.sunlightIndex = sunlightIndex

class Observation:
    def __init__(self):
        self.plainValueObservations = {}
        self.conversionObservations = {}

class TradingState:
    def __init__(self, traderData, timestamp, listings, order_depths,
                 own_trades, market_trades, position, observations):
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings
        self.order_depths = order_depths
        self.own_trades = own_trades
        self.market_trades = market_trades
        self.position = position
        self.observations = observations

# ---------------------------------------------------------------------------
# Position limits
# ---------------------------------------------------------------------------

LIMITS = {
    "HYDROGEL_PACK": 200,
    "VELVETFRUIT_EXTRACT": 200,
    "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300, "VEV_5100": 300,
    "VEV_5200": 300, "VEV_5300": 300, "VEV_5400": 300, "VEV_5500": 300,
    "VEV_6000": 300, "VEV_6500": 300,
}

# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def load_prices(round_num, day):
    """Returns {timestamp: {product: (buy_orders, sell_orders, mid)}}"""
    path = Path(f"data/round{round_num}/prices_round_{round_num}_day_{day}.csv")
    data = defaultdict(dict)
    with open(path) as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ts = int(row["timestamp"])
            product = row["product"]
            od = OrderDepth()
            for i in ["1", "2", "3"]:
                bp, bv = row.get(f"bid_price_{i}", ""), row.get(f"bid_volume_{i}", "")
                ap, av = row.get(f"ask_price_{i}", ""), row.get(f"ask_volume_{i}", "")
                if bp and bv:
                    od.buy_orders[int(float(bp))] = int(float(bv))
                if ap and av:
                    od.sell_orders[int(float(ap))] = -int(float(av))  # negative convention
            mid = float(row["mid_price"]) if row["mid_price"] else None
            data[ts][product] = (od, mid)
    return data


def load_trades(round_num, day):
    """Returns {timestamp: [Trade, ...]}"""
    path = Path(f"data/round{round_num}/trades_round_{round_num}_day_{day}.csv")
    data = defaultdict(list)
    with open(path) as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            ts = int(row["timestamp"])
            data[ts].append(Trade(
                symbol=row["symbol"],
                price=int(float(row["price"])),
                quantity=int(float(row["quantity"])),
                buyer=row["buyer"],
                seller=row["seller"],
                timestamp=ts,
            ))
    return data


# ---------------------------------------------------------------------------
# Order matching
# ---------------------------------------------------------------------------

def match_orders(orders, price_data, market_trades_at_ts, positions):
    """
    Returns (fills, position_violations).
    fills: list of Trade representing our executions.

    Matching logic:
      1. Active take: buy order at P >= best ask → fill at ask price (best ask first).
         sell order at P <= best bid → fill at bid price.
      2. Passive: market trade at price P with qty Q →
         our buy at >= P fills at our quoted price (we get filled at our quote).
         our sell at <= P fills at our quoted price.
    Fill quantities are capped by position limits.
    """
    fills = []
    violations = []

    for product, product_orders in orders.items():
        if not product_orders:
            continue

        limit = LIMITS.get(product, 9999)
        pos = positions.get(product, 0)

        if product not in price_data:
            continue
        od, mid = price_data[product]

        # Separate buys and sells; enforce limit pre-check
        buys = sorted([o for o in product_orders if o.quantity > 0], key=lambda o: -o.price)
        sells = sorted([o for o in product_orders if o.quantity < 0], key=lambda o: o.price)

        total_buy_qty = sum(o.quantity for o in buys)
        total_sell_qty = sum(abs(o.quantity) for o in sells)
        if pos + total_buy_qty > limit or pos - total_sell_qty < -limit:
            violations.append(product)

        # --- Active takes against the book ---
        book_asks = sorted(od.sell_orders.keys())   # ascending — best ask first
        book_bids = sorted(od.buy_orders.keys(), reverse=True)

        remaining_buys = {o.price: o.quantity for o in buys}
        remaining_sells = {o.price: abs(o.quantity) for o in sells}

        # Buy orders take from book asks
        for ask_px in book_asks:
            avail = abs(od.sell_orders[ask_px])
            for our_px in sorted(remaining_buys.keys(), reverse=True):
                if our_px < ask_px:
                    break
                if remaining_buys[our_px] <= 0:
                    continue
                qty = min(remaining_buys[our_px], avail)
                if qty <= 0:
                    continue
                # Enforce limit
                qty = min(qty, limit - pos)
                if qty <= 0:
                    break
                fills.append(Trade(product, ask_px, qty, buyer="SUBMISSION", seller="", timestamp=0))
                pos += qty
                remaining_buys[our_px] -= qty
                avail -= qty
            if avail <= 0:
                continue

        # Sell orders take from book bids
        for bid_px in book_bids:
            avail = od.buy_orders[bid_px]
            for our_px in sorted(remaining_sells.keys()):
                if our_px > bid_px:
                    break
                if remaining_sells[our_px] <= 0:
                    continue
                qty = min(remaining_sells[our_px], avail)
                qty = min(qty, pos + limit)
                if qty <= 0:
                    break
                fills.append(Trade(product, bid_px, -qty, buyer="", seller="SUBMISSION", timestamp=0))
                pos -= qty
                remaining_sells[our_px] -= qty
                avail -= qty

        # --- Passive fills from market trades ---
        for mt in market_trades_at_ts:
            if mt.symbol != product:
                continue
            p, q = mt.price, mt.quantity

            # A market trade at p means someone bought at p → our sell at <= p fills
            for our_px in sorted(remaining_sells.keys()):
                if our_px > p:
                    continue
                qty = min(remaining_sells[our_px], q)
                qty = min(qty, pos + limit)
                if qty <= 0:
                    continue
                fills.append(Trade(product, our_px, -qty, buyer="", seller="SUBMISSION", timestamp=0))
                pos -= qty
                remaining_sells[our_px] -= qty
                q -= qty

            # A market trade at p means someone sold at p → our buy at >= p fills
            q = mt.quantity
            for our_px in sorted(remaining_buys.keys(), reverse=True):
                if our_px < p:
                    continue
                qty = min(remaining_buys[our_px], q)
                qty = min(qty, limit - pos)
                if qty <= 0:
                    continue
                fills.append(Trade(product, our_px, qty, buyer="SUBMISSION", seller="", timestamp=0))
                pos += qty
                remaining_buys[our_px] -= qty
                q -= qty

        positions[product] = pos

    return fills, violations


# ---------------------------------------------------------------------------
# Single-day simulation
# ---------------------------------------------------------------------------

def run_day(trader, round_num, day, positions, trader_data, carry_cash=None):
    price_data_by_ts = load_prices(round_num, day)
    trade_data_by_ts = load_trades(round_num, day)

    all_timestamps = sorted(set(price_data_by_ts.keys()) | set(trade_data_by_ts.keys()))

    listings = {
        p: Listing(p, p, "XIRECS")
        for p in set(prod for ts_data in price_data_by_ts.values() for prod in ts_data)
    }

    cash = carry_cash if carry_cash is not None else 0.0
    own_trades_prev = defaultdict(list)
    pnl_log = []  # (timestamp, product, fill_price, qty, cash_delta)

    for ts in all_timestamps:
        price_data = price_data_by_ts.get(ts, {})
        market_trades = trade_data_by_ts.get(ts, [])

        order_depths = {prod: od for prod, (od, _) in price_data.items()}
        market_trades_by_sym = defaultdict(list)
        for t in market_trades:
            market_trades_by_sym[t.symbol].append(t)

        state = TradingState(
            traderData=trader_data,
            timestamp=ts,
            listings=listings,
            order_depths=order_depths,
            own_trades=dict(own_trades_prev),
            market_trades=dict(market_trades_by_sym),
            position={k: v for k, v in positions.items() if v != 0},
            observations=Observation(),
        )

        try:
            orders, conversions, trader_data = trader.run(state)
        except Exception as e:
            print(f"  [ERROR] t={ts}: {e}", file=sys.stderr)
            own_trades_prev = defaultdict(list)
            continue

        pos_copy = dict(positions)
        fills, violations = match_orders(orders, price_data, market_trades, pos_copy)
        positions.update(pos_copy)

        if violations:
            print(f"  [LIMIT] t={ts}: position limit violated for {violations}, orders dropped")

        own_trades_prev = defaultdict(list)
        for fill in fills:
            own_trades_prev[fill.symbol].append(fill)
            delta = -fill.price * fill.quantity  # negative qty = sell = positive cash
            cash += delta
            pnl_log.append((ts, fill.symbol, fill.price, fill.quantity, delta))

    # Mark-to-market at end of day
    mtm = 0.0
    last_mids = {}
    for ts in reversed(all_timestamps):
        for prod, (od, mid) in price_data_by_ts.get(ts, {}).items():
            if prod not in last_mids and mid is not None:
                last_mids[prod] = mid
        if len(last_mids) >= len(listings):
            break

    for prod, pos in positions.items():
        if pos != 0 and prod in last_mids:
            mtm += pos * last_mids[prod]

    return cash, mtm, pnl_log, trader_data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_trader(path):
    trader_path = Path(path).resolve()
    # Add trader's directory to path so 'from datamodel import ...' works
    sys.path.insert(0, str(trader_path.parent))
    spec = importlib.util.spec_from_file_location("trader_module", trader_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module.Trader()


def main():
    parser = argparse.ArgumentParser(description="Local round-4 backtester")
    parser.add_argument("trader", help="Path to trader .py file")
    parser.add_argument("--round", type=int, default=4)
    parser.add_argument("--days", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--merge-pnl", action="store_true",
                        help="Carry cash and positions forward across days")
    args = parser.parse_args()

    trader = load_trader(args.trader)
    print(f"Loaded trader: {args.trader}")
    print(f"Round {args.round}, days: {args.days}\n")

    positions = defaultdict(int)
    trader_data = ""
    carry_cash = 0.0
    total_cash = 0.0
    total_mtm = 0.0

    for day in args.days:
        if not args.merge_pnl:
            positions = defaultdict(int)
            trader_data = ""
            carry_cash = None

        print(f"--- Day {day} ---")
        cash, mtm, pnl_log, trader_data = run_day(
            trader, args.round, day, positions, trader_data,
            carry_cash=carry_cash if args.merge_pnl else None,
        )
        if args.merge_pnl:
            carry_cash = cash

        realized = cash
        total_pnl = realized + mtm

        # Per-product breakdown
        by_product = defaultdict(lambda: {"cash": 0.0, "fills": 0})
        for ts, sym, px, qty, delta in pnl_log:
            by_product[sym]["cash"] += delta
            by_product[sym]["fills"] += 1

        for prod, stats in sorted(by_product.items()):
            pos = positions.get(prod, 0)
            mid = None
            # find last mid
            price_data_by_ts = load_prices(args.round, day)
            for ts in reversed(sorted(price_data_by_ts.keys())):
                if prod in price_data_by_ts[ts]:
                    mid = price_data_by_ts[ts][prod][1]
                    break
            prod_mtm = pos * mid if (mid and pos) else 0
            prod_total = stats["cash"] + prod_mtm
            print(f"  {prod:<30} fills={stats['fills']:4d}  realized={stats['cash']:>10.1f}"
                  f"  pos={pos:>5}  mtm={prod_mtm:>10.1f}  total={prod_total:>10.1f}")

        print(f"  {'TOTAL':<30}        realized={realized:>10.1f}"
              f"         mtm={mtm:>10.1f}  total={total_pnl:>10.1f}\n")

        total_cash += realized
        total_mtm += mtm

    if len(args.days) > 1:
        print(f"=== All days combined ===")
        print(f"  Realized: {total_cash:>10.1f}")
        print(f"  MTM:      {total_mtm:>10.1f}")
        print(f"  Total:    {total_cash + total_mtm:>10.1f}")


if __name__ == "__main__":
    main()
