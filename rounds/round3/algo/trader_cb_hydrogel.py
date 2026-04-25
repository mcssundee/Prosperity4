import json
from datamodel import Order, TradingState
from typing import List

HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20
HYDRO_EMA_ALPHA  = 0.001   # very slow — anchors near 10k, adapts only to genuine regime shifts
HYDRO_FAIR_INIT  = 10000.0

# Offsets from dynamic fair value (EMA of microprice).
# Buy: mid < fair + offset → target long position
HYDRO_BUY_OFFSETS = [
    (-75, 70),
    (-70, 60),
    (-65, 50),
    (-60, 40),
]

# Sell: mid > fair + offset → target short position
HYDRO_SELL_OFFSETS = [
    (40, 70),
    (35, 60),
    (30, 50),
    (25, 40),
]

HYDRO_NEUTRAL_FLATTEN = False
HYDRO_FLATTEN_TRIGGER = 30


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
    def bid(self):
        return 1

    def run(self, state: TradingState):
        saved = {}
        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                pass

        result = {}
        hydro_orders = self.hydro_range_strategy(state, saved)
        if hydro_orders:
            result["HYDROGEL_PACK"] = hydro_orders

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def hydro_range_strategy(self, state: TradingState, saved: dict) -> list:
        product = "HYDROGEL_PACK"
        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread = best_ask - best_bid

        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        mid = (best_bid + best_ask) / 2.0

        # Slow EMA of mid — barely drifts from 10k, only tracks genuine regime shifts
        prev_ema = saved.get("h_ema", HYDRO_FAIR_INIT)
        ema = HYDRO_EMA_ALPHA * mid + (1 - HYDRO_EMA_ALPHA) * prev_ema
        saved["h_ema"] = round(ema, 4)
        pos = state.position.get(product, 0)

        # Emergency unwind: price escaped far from fair value
        if mid < ema - 180 and pos > 0:
            logger.print(f"EMERGENCY UNWIND LONG: mid={mid} ema={ema:.1f} pos={pos}")
            return [Order(product, int(best_bid), -pos)]
        if mid > ema + 100 and pos < 0:
            logger.print(f"EMERGENCY UNWIND SHORT: mid={mid} ema={ema:.1f} pos={pos}")
            return [Order(product, int(best_ask), -pos)]

        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos
        orders: List[Order] = []

        for offset, target in HYDRO_BUY_OFFSETS:
            if mid < ema + offset:
                qty = min(HYDRO_STEP_SIZE, target - pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))
                break

        if not orders:
            for offset, target in HYDRO_SELL_OFFSETS:
                if mid > ema + offset:
                    qty = min(HYDRO_STEP_SIZE, pos + target, sell_room)
                    if qty > 0:
                        orders.append(Order(product, int(best_bid), -qty))
                    break

        if not orders and HYDRO_NEUTRAL_FLATTEN:
            if pos > HYDRO_FLATTEN_TRIGGER:
                qty = min(HYDRO_STEP_SIZE, pos, sell_room)
                if qty > 0:
                    orders.append(Order(product, int(best_bid), -qty))
            elif pos < -HYDRO_FLATTEN_TRIGGER:
                qty = min(HYDRO_STEP_SIZE, -pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))

        return orders
