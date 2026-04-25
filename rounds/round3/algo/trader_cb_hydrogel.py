import json
from datamodel import Order, TradingState
from typing import Dict, List, Optional

HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20

HYDRO_BUY_TIERS = [
    (9925, 70),
    (9930, 60),
    (9935, 50),
    (9940, 40),
]

HYDRO_SELL_TIERS = [
    (10040, 70),
    (10035, 60),
    (10030, 50),
    (10025, 40),
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
        result: Dict[str, List[Order]] = {}

        hydro_orders = self.hydro_range_strategy(state)
        if hydro_orders:
            result["HYDROGEL_PACK"] = hydro_orders

        trader_data = ""
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def hydro_range_strategy(self, state: TradingState) -> list:
        product = "HYDROGEL_PACK"
        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread = best_ask - best_bid

        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        mid = (best_bid + best_ask) / 2
        pos = state.position.get(product, 0)

        if mid < 9820 and pos > 0:
            logger.print(f"EMERGENCY UNWIND LONG: mid={mid} pos={pos}")
            return [Order(product, int(best_bid), -pos)]
        if mid > 10100 and pos < 0:
            logger.print(f"EMERGENCY UNWIND SHORT: mid={mid} pos={pos}")
            return [Order(product, int(best_ask), -pos)]

        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos
        orders = []

        for threshold, target in HYDRO_BUY_TIERS:
            if mid < threshold:
                qty = min(HYDRO_STEP_SIZE, target - pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))
                break

        if not orders:
            for threshold, target in HYDRO_SELL_TIERS:
                if mid > threshold:
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
