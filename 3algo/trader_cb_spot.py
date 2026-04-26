import json
from datamodel import Order, TradingState
from typing import Dict, List, Optional

SPOT = "VELVETFRUIT_EXTRACT"
SPOT_LIMIT = 200
SPOT_ALPHA = 0.02
SPOT_ACTIVE_THR = 2.0
SPOT_QUOTE_LIMIT = 15


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


def update_ema(prev: Optional[float], price: float, alpha: float) -> float:
    return price if prev is None else alpha * price + (1 - alpha) * prev


def spot_orders(depth, ema: float, pos: int) -> List[Order]:
    orders = []
    best_ask = min(depth.sell_orders)
    best_bid = max(depth.buy_orders)

    if best_ask < ema - SPOT_ACTIVE_THR:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT - pos)
        if qty > 0:
            orders.append(Order(SPOT, best_ask, qty))
    if best_bid > ema + SPOT_ACTIVE_THR:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT + pos)
        if qty > 0:
            orders.append(Order(SPOT, best_bid, -qty))

    quote_bid = best_bid + 1
    quote_ask = best_ask - 1
    if quote_bid < ema:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT - pos)
        if qty > 0:
            orders.append(Order(SPOT, quote_bid, qty))
    if quote_ask > ema:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT + pos)
        if qty > 0:
            orders.append(Order(SPOT, quote_ask, -qty))

    return orders


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

        result: Dict[str, List[Order]] = {}

        depth = state.order_depths.get(SPOT)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
            spot_ema = update_ema(saved.get("se"), mid, SPOT_ALPHA)
            saved["se"] = round(spot_ema, 2)
            pos = state.position.get(SPOT, 0)
            orders = spot_orders(depth, spot_ema, pos)
            if orders:
                result[SPOT] = orders

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
