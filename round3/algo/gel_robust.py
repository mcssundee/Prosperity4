import json
from datamodel import Order, TradingState
from typing import List

HYDRO_POS_LIM      = 200
HYDRO_STEP_SIZE    = 20
HYDRO_MAX_SPREAD   = 20

# EMA alphas — all applied every tick (100ms), so:
#   0.001 ≈ 693-tick (~70s) halflife
#   0.01  ≈ 69-tick  (~7s)  halflife
HYDRO_FAIR_ALPHA   = 0.001  # rolling fair value (slow EMA of microprice)
HYDRO_FAST_ALPHA   = 0.01   # fast trend EMA
HYDRO_SLOW_ALPHA   = 0.001  # slow trend EMA

HYDRO_POS_SCALE    = 0.92   # position units per tick of deviation from fair
                            # → target ≈ 55 at 60-tick move (matches original tiers)
HYDRO_MIN_DEV      = 20.0   # minimum deviation (ticks) to place any taker order
HYDRO_TREND_THRESH = 10.0   # fast-slow gap (ticks) to classify market as trending
HYDRO_STOP_THRESH  = 15.0   # fast-slow gap to trigger stop-loss on existing position
HYDRO_STOP_POS     = 12     # minimum position size to trigger stop (≈ one maker fill)

HYDRO_MAKER_SIZE    = 12
HYDRO_MAKER_MAX_POS = 15


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
        saved = {}
        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                pass

        result = {}
        hydro_orders = self.hydro_strategy(state, saved)
        if hydro_orders:
            result["HYDROGEL_PACK"] = hydro_orders

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def hydro_strategy(self, state: TradingState, saved: dict) -> List[Order]:
        product = "HYDROGEL_PACK"
        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread = best_ask - best_bid

        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        bid_vol = od.buy_orders[best_bid]
        ask_vol = abs(od.sell_orders[best_ask])
        total_vol = bid_vol + ask_vol
        microprice = (best_bid * ask_vol + best_ask * bid_vol) / total_vol if total_vol > 0 else (best_bid + best_ask) / 2.0

        pos = state.position.get(product, 0)

        # Update EMAs from persisted state
        fair = saved.get("hydro_fair", microprice)
        fast = saved.get("hydro_fast", microprice)
        slow = saved.get("hydro_slow", microprice)

        fair = HYDRO_FAIR_ALPHA * microprice + (1 - HYDRO_FAIR_ALPHA) * fair
        fast = HYDRO_FAST_ALPHA * microprice + (1 - HYDRO_FAST_ALPHA) * fast
        slow = HYDRO_SLOW_ALPHA * microprice + (1 - HYDRO_SLOW_ALPHA) * slow

        saved["hydro_fair"] = fair
        saved["hydro_fast"] = fast
        saved["hydro_slow"] = slow

        # Positive deviation → price below fair → buy signal
        deviation   = fair - microprice
        trend_gap   = fast - slow          # positive = uptrend, negative = downtrend
        trending_up   = trend_gap >  HYDRO_TREND_THRESH
        trending_down = trend_gap < -HYDRO_TREND_THRESH

        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos
        orders: List[Order] = []

        # Stop-loss: exit if a sizable position is caught in a strong opposing trend.
        # Reduces at 2× normal step size to get out faster than we got in.
        if pos > 50 and trend_gap < -HYDRO_STOP_THRESH:
            qty = min(HYDRO_STEP_SIZE * 2, pos)
            orders.append(Order(product, best_bid, -qty))
            return orders
        if pos < -50 and trend_gap > HYDRO_STOP_THRESH:
            qty = min(HYDRO_STEP_SIZE * 2, -pos)
            orders.append(Order(product, best_ask, qty))
            return orders

        # Continuous position target: linear in deviation, clamped to limits.
        # Gate on minimum deviation so sub-threshold noise never triggers a taker order.
        if abs(deviation) < HYDRO_MIN_DEV:
            delta = 0
        else:
            raw_target = deviation * HYDRO_POS_SCALE
            target_pos = int(max(-HYDRO_POS_LIM, min(HYDRO_POS_LIM, raw_target)))
            delta = target_pos - pos
            delta = max(-HYDRO_STEP_SIZE, min(HYDRO_STEP_SIZE, delta))

        # Trend filter: only take mean-reversion trades when not in a trend.
        # Lets existing positions ride; only blocks new entries.
        if delta > 0 and not trending_down:
            qty = min(delta, buy_room)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))
        elif delta < 0 and not trending_up:
            qty = min(-delta, sell_room)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))

        # Maker: passive quotes only when flat and no taker order was placed.
        if not orders and spread >= 4 and abs(pos) <= HYDRO_MAKER_MAX_POS:
            quote_bid = best_bid + 1
            quote_ask = best_ask - 1
            if quote_bid < quote_ask:
                if buy_room > 0:
                    orders.append(Order(product, quote_bid, min(HYDRO_MAKER_SIZE, buy_room)))
                if sell_room > 0:
                    orders.append(Order(product, quote_ask, -min(HYDRO_MAKER_SIZE, sell_room)))

        return orders
