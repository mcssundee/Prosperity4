from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json
import math
from collections import defaultdict


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

VOUCHER_STRIKES = {
    'VEV_4000': 4000, 'VEV_4500': 4500,
    'VEV_5000': 5000, 'VEV_5100': 5100,
    'VEV_5200': 5200, 'VEV_5300': 5300,
    'VEV_5400': 5400, 'VEV_5500': 5500,
    'VEV_6000': 6000, 'VEV_6500': 6500,
}
VOUCHER_MM = {
    'VEV_4000': (300, 5), 'VEV_4500': (300, 5),
    'VEV_5000': (200, 3), 'VEV_5100': (200, 3),
    'VEV_5200': (100, 2), 'VEV_5300': (100, 2),
    'VEV_5400': (50,  1), 'VEV_5500': (50,  1),
}


class Trader:
    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        opt_orders, opt_data = self.vev_options(state, shared)
        for sym, orders in opt_orders.items():
            result[sym] = orders

        traderData = json.dumps(opt_data)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def vev_options(self, state: TradingState, shared: dict):
        result = defaultdict(list)
        mid_hist = shared.get("vev_opt_mid_hist", {})

        for sym, (pos_lim, quote_qty) in VOUCHER_MM.items():
            if sym not in state.order_depths:
                continue
            od = state.order_depths[sym]
            if not od.buy_orders or not od.sell_orders:
                continue
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            mid = (best_bid + best_ask) / 2.0

            K = VOUCHER_STRIKES[sym]
            win = 13 if K <= 4500 else (11 if K <= 5100 else 15)
            hist = mid_hist.get(sym, [])
            hist.append(mid)
            if len(hist) > win:
                hist.pop(0)
            mid_hist[sym] = hist
            fair = sum(hist) / len(hist)
            fair_int = round(fair)

            pos = state.position.get(sym, 0)
            buy_cap = pos_lim - pos
            sell_cap = pos_lim + pos

            if buy_cap > 0:
                result[sym].append(Order(sym, fair_int - 1, min(quote_qty, buy_cap)))
            if sell_cap > 0:
                result[sym].append(Order(sym, fair_int + 1, -min(quote_qty, sell_cap)))

        return result, {"vev_opt_mid_hist": mid_hist}
