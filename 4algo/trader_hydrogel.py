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

        result['HYDROGEL_PACK'], hp_data = self.hydrogel(state, shared)

        traderData = json.dumps(hp_data)
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    def hydrogel(self, state: TradingState, shared: dict):
        product     = 'HYDROGEL_PACK'
        result      = []
        pos_lim     = 200
        quote_size  = 25     # per level
        half_spread = 4
        fv_window   = 20
        flat_thr    = 25     # quote both sides when |pos| < flat_thr
        unwind_thr  = 80     # cross spread when |pos| > unwind_thr

        mid_hist = shared.get('hp_mid_hist', [])

        if product not in state.order_depths:
            return result, {'hp_mid_hist': mid_hist}

        od   = state.order_depths[product]
        pos  = state.position.get(product, 0)
        bids = sorted(od.buy_orders, reverse=True)
        asks = sorted(od.sell_orders)

        best_bid = bids[0] if bids else None
        best_ask = asks[0] if asks else None

        if best_bid is not None and best_ask is not None:
            mid_hist.append((best_bid + best_ask) / 2.0)
        if len(mid_hist) > fv_window:
            mid_hist = mid_hist[-fv_window:]

        fair     = round(sum(mid_hist) / len(mid_hist)) if mid_hist else 10000
        buy_cap  = pos_lim - pos
        sell_cap = pos_lim + pos

        bid_px = fair - half_spread
        ask_px = fair + half_spread
        if best_ask is not None:
            bid_px = min(bid_px, best_ask - 1)
        if best_bid is not None:
            ask_px = max(ask_px, best_bid + 1)

        if pos > unwind_thr and sell_cap > 0 and bids:
            qty = min(sell_cap, quote_size, od.buy_orders[bids[0]])
            result.append(Order(product, bids[0], -qty))
            return result, {'hp_mid_hist': mid_hist}

        if pos < -unwind_thr and buy_cap > 0 and asks:
            qty = min(buy_cap, quote_size, abs(od.sell_orders[asks[0]]))
            result.append(Order(product, asks[0], qty))
            return result, {'hp_mid_hist': mid_hist}

        if pos >= flat_thr:
            if sell_cap > 0:
                result.append(Order(product, ask_px, -min(quote_size, sell_cap)))
        elif pos <= -flat_thr:
            if buy_cap > 0:
                result.append(Order(product, bid_px, min(quote_size, buy_cap)))
        else:
            if buy_cap > 0:
                result.append(Order(product, bid_px, min(quote_size, buy_cap)))
            if sell_cap > 0:
                result.append(Order(product, ask_px, -min(quote_size, sell_cap)))

        return result, {'hp_mid_hist': mid_hist}
