import json
from datamodel import Order, TradingState
from typing import List

HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20
HYDRO_FAIR_ALPHA = 0.001  # slow EMA — ~693-tick halflife (~70s)
HYDRO_MIN_DEV    = 20.0   # minimum deviation (ticks) before taker fires
HYDRO_POS_SCALE  = 0.92   # units per tick of deviation; 60 ticks → ~55 units

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
        orders = self.hydro_strategy(state, saved)
        if orders:
            result["HYDROGEL_PACK"] = orders

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
        if spread <= 0 or spread > HYDRO_MAX_SPREAD:
            return []

        bid_vol = od.buy_orders[best_bid]
        ask_vol = abs(od.sell_orders[best_ask])
        total_vol = bid_vol + ask_vol
        microprice = (best_bid * ask_vol + best_ask * bid_vol) / total_vol if total_vol > 0 else (best_bid + best_ask) / 2.0

        pos = state.position.get(product, 0)
        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos

        fair = saved.get("hydro_fair", microprice)
        fair = HYDRO_FAIR_ALPHA * microprice + (1 - HYDRO_FAIR_ALPHA) * fair
        saved["hydro_fair"] = fair

        deviation = fair - microprice
        orders: List[Order] = []

        # Taker: fade moves away from fair value once deviation is large enough.
        if abs(deviation) >= HYDRO_MIN_DEV:
            raw_target = deviation * HYDRO_POS_SCALE
            target = int(max(-HYDRO_POS_LIM, min(HYDRO_POS_LIM, raw_target)))
            delta = max(-HYDRO_STEP_SIZE, min(HYDRO_STEP_SIZE, target - pos))
            if delta > 0:
                qty = min(delta, buy_room)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
            elif delta < 0:
                qty = min(-delta, sell_room)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

        # Maker: passive quotes inside the spread when position is near flat.
        if not orders and spread >= 4 and abs(pos) <= HYDRO_MAKER_MAX_POS:
            quote_bid = best_bid + 1
            quote_ask = best_ask - 1
            if quote_bid < quote_ask:
                if buy_room > 0:
                    orders.append(Order(product, quote_bid, min(HYDRO_MAKER_SIZE, buy_room)))
                if sell_room > 0:
                    orders.append(Order(product, quote_ask, -min(HYDRO_MAKER_SIZE, sell_room)))

        return orders
