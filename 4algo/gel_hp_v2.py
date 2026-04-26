from datamodel import OrderDepth, TradingState, Order
from typing import List
import json

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

CENTER = 10000
EOD_START = 990_000
EOD_HARD  = 999_900


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
        quote_size = 8
        # How far from CENTER before we lean harder on inventory skew
        inv_skew_div = 20   # 1 tick per 20 units of position
        mr_skew_div  = 25   # 1 tick per 25 units deviation from CENTER

        last_m38_ts = shared.get('last_m38_ts', state.timestamp)

        od = state.order_depths.get(product)
        if not od or not od.buy_orders or not od.sell_orders:
            return [], {'last_m38_ts': last_m38_ts}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0

        # Track Mark 38 timing for size boost
        m38_now = [t for t in state.market_trades.get(product, [])
                   if t.buyer == 'Mark 38' or t.seller == 'Mark 38']
        if m38_now:
            last_m38_ts = state.timestamp
        gap = state.timestamp - last_m38_ts
        size_boost = 2 if gap >= 600 else 1

        pos = state.position.get(product, 0)
        buy_cap = pos_lim - pos
        sell_cap = pos_lim + pos
        ts = state.timestamp
        orders = []

        # --- EOD flattening: hit every available level to close position ---
        if ts >= EOD_START and pos != 0:
            remaining = abs(pos)
            if pos > 0:  # long — need to sell; hit all bids
                for bid in sorted(od.buy_orders, reverse=True):
                    if sell_cap <= 0 or remaining <= 0:
                        break
                    qty = min(sell_cap, remaining, od.buy_orders[bid])
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    remaining -= qty
            else:  # short — need to buy; lift all asks
                for ask in sorted(od.sell_orders):
                    if buy_cap <= 0 or remaining <= 0:
                        break
                    qty = min(buy_cap, remaining, abs(od.sell_orders[ask]))
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    remaining -= qty
            return orders, {'last_m38_ts': last_m38_ts}

        # --- Aggressive take: mean-reversion when price far from CENTER ---
        # buy when ask is well below CENTER, sell when bid is well above CENTER
        for ask in sorted(od.sell_orders):
            if ask < CENTER - 8 and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                orders.append(Order(product, ask, qty))
                buy_cap -= qty
        for bid in sorted(od.buy_orders, reverse=True):
            if bid > CENTER + 8 and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                orders.append(Order(product, bid, -qty))
                sell_cap -= qty

        # --- Passive inside-spread quotes ---
        # Post one tick inside best bid/ask so we're always first in queue
        # Combined inventory + mean-reversion skew
        inv_skew = -round(pos / inv_skew_div)
        mr_skew  = -round((mid - CENTER) / mr_skew_div)
        skew = inv_skew + mr_skew

        bid_px = best_bid + 1 + skew
        ask_px = best_ask - 1 + skew

        # Safety guards: never cross, never worse than best book price
        if bid_px >= ask_px:
            bid_px = ask_px - 1
        # Don't quote above best_ask or below best_bid (would cross the market)
        bid_px = min(bid_px, best_ask - 1)
        ask_px = max(ask_px, best_bid + 1)

        qs = quote_size * size_boost
        if buy_cap > 0:
            orders.append(Order(product, bid_px, min(qs, buy_cap)))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -min(qs, sell_cap)))

        return orders, {'last_m38_ts': last_m38_ts}
