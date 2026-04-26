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

EOD_START = 990_000

# Slow EMA of mid price — used as adaptive fair value for mean-reversion takes.
# Alpha=0.002 ≈ 500-tick half-life; tracks intraday drift without chasing noise.
EMA_ALPHA = 0.002

# Symmetric take threshold in ticks (applied to the ema, not hardcoded 10000).
# We buy aggressively when best_ask is this many ticks below ema,
# and sell aggressively when best_bid is this many ticks above ema.
# 8 ticks ≈ half the 16-tick spread — only fires when price is meaningfully dislocated.
TAKE_THRESH = 8

# Passive quote skew parameters.
# Inventory skew: shift quotes 1 tick per INV_DIV units of open position.
# Mean-rev skew: shift quotes 1 tick per MR_DIV ticks of mid deviation from ema.
# Both pull the quotes toward zero inventory and toward fair value.
INV_DIV = 30
MR_DIV  = 20


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

        ema = shared.get('hp_ema')
        last_m38_ts = shared.get('last_m38_ts', state.timestamp)

        od = state.order_depths.get(product)
        if not od or not od.buy_orders or not od.sell_orders:
            return [], {'hp_ema': ema, 'last_m38_ts': last_m38_ts}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0

        # Adaptive fair value: slow EMA tracks intraday drift
        ema = mid if ema is None else EMA_ALPHA * mid + (1 - EMA_ALPHA) * ema
        fair = ema

        # Mark 38 timing: size up when they're statistically due (median gap ~700ts)
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
        if ts >= EOD_START and pos != 0:
            remaining = abs(pos)
            if pos > 0:
                for bid in sorted(od.buy_orders, reverse=True):
                    if sell_cap <= 0 or remaining <= 0:
                        break
                    qty = min(sell_cap, remaining, od.buy_orders[bid])
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty
                    remaining -= qty
            else:
                for ask in sorted(od.sell_orders):
                    if buy_cap <= 0 or remaining <= 0:
                        break
                    qty = min(buy_cap, remaining, abs(od.sell_orders[ask]))
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
                    remaining -= qty
            return orders, {'hp_ema': ema, 'last_m38_ts': last_m38_ts}

        # --- Aggressive take: symmetric mean-reversion around adaptive fair ---
        # Buy when ask is meaningfully below fair (price dislocated low).
        # Sell when bid is meaningfully above fair (price dislocated high).
        for ask in sorted(od.sell_orders):
            if ask < fair - TAKE_THRESH and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                orders.append(Order(product, ask, qty))
                buy_cap -= qty
        for bid in sorted(od.buy_orders, reverse=True):
            if bid > fair + TAKE_THRESH and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                orders.append(Order(product, bid, -qty))
                sell_cap -= qty

        # --- Passive inside-spread quotes ---
        # Post 1 tick inside best bid/ask — we become the sole best bid/ask,
        # so Mark 38 (who always hits best bid/ask) fills us every visit.
        # Skew both sides by inventory + mean-reversion signal to stay flat.
        inv_skew = -round(pos / INV_DIV)
        mr_skew  = -round((mid - fair) / MR_DIV)
        skew = inv_skew + mr_skew

        bid_px = best_bid + 1 + skew
        ask_px = best_ask - 1 + skew

        # Guards: never cross, never outside the existing book
        bid_px = min(bid_px, best_ask - 1)
        ask_px = max(ask_px, best_bid + 1)
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        if buy_cap > 0:
            orders.append(Order(product, bid_px, min(qs, buy_cap)))
        if sell_cap > 0:
            orders.append(Order(product, ask_px, -min(qs, sell_cap)))

        return orders, {'hp_ema': ema, 'last_m38_ts': last_m38_ts}
