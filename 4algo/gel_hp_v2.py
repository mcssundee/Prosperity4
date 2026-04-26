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

# HYDROGEL_PACK observed fair value across all 3 days of data: mean ≈ 9995,
# range 9891–10081. 10000 is the known long-run center used for mean-reversion.
FAIR = 10000

# Symmetric take threshold: fire when best_ask < FAIR-THRESH (buy) or
# best_bid > FAIR+THRESH (sell). The spread is 16 ticks wide so best_ask =
# mid+8 — a threshold of 8 means we take when mid < FAIR-16 or mid > FAIR+16.
TAKE_THRESH = 8

EOD_START = 990_000


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

        last_m38_ts = shared.get('last_m38_ts', state.timestamp)

        od = state.order_depths.get(product)
        if not od or not od.buy_orders or not od.sell_orders:
            return [], {'last_m38_ts': last_m38_ts}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0

        # Mark 38 timing: size up when statistically due (median gap ~700ts)
        m38_now = [t for t in state.market_trades.get(product, [])
                   if t.buyer == 'Mark 38' or t.seller == 'Mark 38']
        if m38_now:
            last_m38_ts = state.timestamp
        gap = state.timestamp - last_m38_ts
        qs = quote_size * (2 if gap >= 600 else 1)

        pos = state.position.get(product, 0)
        buy_cap = pos_lim - pos
        sell_cap = pos_lim + pos
        ts = state.timestamp
        orders = []

        # --- EOD: hit every available level to close position flat ---
        # Always run during EOD window regardless of position size.
        if ts >= EOD_START:
            if pos > 0:
                remaining = pos
                for bid in sorted(od.buy_orders, reverse=True):
                    if sell_cap <= 0 or remaining <= 0:
                        break
                    qty = min(sell_cap, remaining, od.buy_orders[bid])
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    remaining -= qty
            elif pos < 0:
                remaining = -pos
                for ask in sorted(od.sell_orders):
                    if buy_cap <= 0 or remaining <= 0:
                        break
                    qty = min(buy_cap, remaining, abs(od.sell_orders[ask]))
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    remaining -= qty
            return orders, {'last_m38_ts': last_m38_ts}

        # --- Aggressive take: mean-reversion around FAIR=10000 ---
        # Price AC = -0.12: mildly mean-reverting. We take when the dislocation
        # is large enough to be worth the inventory risk (TAKE_THRESH ticks).
        # With spread=16, best_ask = mid+8, so ask < FAIR-8 means mid < FAIR-16.
        for ask in sorted(od.sell_orders):
            if ask < FAIR - TAKE_THRESH and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                orders.append(Order(product, ask, qty))
                buy_cap -= qty
        for bid in sorted(od.buy_orders, reverse=True):
            if bid > FAIR + TAKE_THRESH and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                orders.append(Order(product, bid, -qty))
                sell_cap -= qty

        # --- Passive inside-spread quotes ---
        # Post 1 tick inside best bid/ask — we become the sole best bid/ask.
        # Mark 38 always hits the best bid/ask, so they fill us on every visit.
        # Spread is 16 ticks; posting at +1/-1 captures 14 ticks per round trip.
        #
        # Two skews shift both quotes in the same direction:
        #   inv_skew: pulls quotes toward zero position (inventory mean-reversion)
        #   mr_skew:  pulls quotes toward FAIR when price deviates (price mean-reversion)
        inv_skew = -round(pos / 30)
        mr_skew  = -round((mid - FAIR) / 20)
        skew = inv_skew + mr_skew

        bid_px = best_bid + 1 + skew
        ask_px = best_ask - 1 + skew

        # Never cross or step outside the existing book
        bid_px = min(bid_px, best_ask - 1)
        ask_px = max(ask_px, best_bid + 1)
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        if buy_cap > 0:
            orders.append(Order(product, bid_px, min(qs, buy_cap)))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -min(qs, sell_cap)))

        return orders, {'last_m38_ts': last_m38_ts}
