from datamodel import OrderDepth, TradingState, Order
from typing import List
import json
import math


class Logger:
    def __init__(self):
        self.logs = ""

    def print(self, *objects, sep=" ", end="\n"):
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str):
        print(json.dumps([
            [
                state.timestamp,
                state.traderData,
                [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
                {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [state.observations.plainValueObservations, {
                    p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff, o.importTariff, o.sugarPrice, o.sunlightIndex]
                    for p, o in state.observations.conversionObservations.items()
                }],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions,
            trader_data,
            self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:
    def run(self, state: TradingState):
        result = {}
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        result['HYDROGEL_PACK'], hp_data = self.hydrogel(state, shared)

        trader_data = json.dumps(hp_data)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def hydrogel(self, state: TradingState, shared: dict):
        product = 'HYDROGEL_PACK'
        pos_lim = 200
        quote_size = 6
        alpha = 0.05   # EMA decay — tracks slow price drift across days
        take_thresh = 10  # only aggress if obviously mispriced

        ema = shared.get('hp_ema')

        od = state.order_depths.get(product)
        if not od or not od.buy_orders or not od.sell_orders:
            return [], {'hp_ema': ema}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0

        ema = mid if ema is None else alpha * mid + (1 - alpha) * ema
        fair = ema

        pos = state.position.get(product, 0)
        # Shift quotes toward zero when inventory builds (1 tick per 40 units)
        skew = -round(pos / 40)
        bid_px = round(fair - 4 + skew)
        ask_px = round(fair + 4 + skew)
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        buy_cap = pos_lim - pos
        sell_cap = pos_lim + pos
        orders = []

        # Aggressive take on obvious mispricings
        for ask in sorted(od.sell_orders):
            if ask <= fair - take_thresh and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                orders.append(Order(product, ask, qty))
                buy_cap -= qty
        for bid in sorted(od.buy_orders, reverse=True):
            if bid >= fair + take_thresh and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                orders.append(Order(product, bid, -qty))
                sell_cap -= qty

        # Passive quotes to capture Mark 38's spread
        if buy_cap > 0:
            orders.append(Order(product, bid_px, min(quote_size, buy_cap)))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -min(quote_size, sell_cap)))

        # Log Mark 38 activity for backtest analysis
        m38 = [t for t in state.market_trades.get(product, [])
               if t.buyer == 'Mark 38' or t.seller == 'Mark 38']
        if m38:
            logger.print(f"t={state.timestamp} Mark38 trades={len(m38)} fair={fair:.1f} pos={pos} bid={bid_px} ask={ask_px}")

        return orders, {'hp_ema': ema}
