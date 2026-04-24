from datamodel import OrderDepth, UserId, TradingState, Order
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
}

# (position_limit, passive_quote_qty)
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
            except Exception:
                pass

        result['HYDROGEL_PACK'], hp_data = self.hydrogel(state, shared)
        result['VELVETFRUIT_EXTRACT'], vev_data = self.vev_spot(state, shared)
        opt_orders, opt_data = self.vev_options(state, shared)
        for sym, orders in opt_orders.items():
            result[sym] = orders

        traderData = json.dumps({**hp_data, **vev_data, **opt_data})
        logger.flush(state, result, conversions, traderData)
        return result, conversions, traderData

    # ------------------------------------------------------------------
    # HYDROGEL_PACK — mean-reversion MM around fixed fair = 10000
    # ------------------------------------------------------------------
    def hydrogel(self, state: TradingState, shared: dict):
        product = 'HYDROGEL_PACK'
        result = []
        pos_lim = 200
        quote_lim = 20
        fair = 10000

        if product not in state.order_depths:
            return result, {}

        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        bids = sorted(od.buy_orders, reverse=True)
        asks = sorted(od.sell_orders)
        buy_cap = pos_lim - pos
        sell_cap = pos_lim + pos

        for ask in asks:
            if ask < fair and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                result.append(Order(product, ask, qty))
                buy_cap -= qty
        for bid in bids:
            if bid > fair and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                result.append(Order(product, bid, -qty))
                sell_cap -= qty

        if buy_cap > 0:
            result.append(Order(product, fair - 1, min(quote_lim, buy_cap)))
        if sell_cap > 0:
            result.append(Order(product, fair + 1, -min(quote_lim, sell_cap)))

        return result, {}

    # ------------------------------------------------------------------
    # VELVETFRUIT_EXTRACT — SMA-5 mid-price market maker
    # ------------------------------------------------------------------
    def vev_spot(self, state: TradingState, shared: dict):
        product = 'VELVETFRUIT_EXTRACT'
        result = []
        pos_lim = 200
        quote_lim = 10
        sma_window = 5

        bid_hist = shared.get("vev_bid_hist", [])
        ask_hist = shared.get("vev_ask_hist", [])

        if product not in state.order_depths:
            return result, {"vev_bid_hist": bid_hist, "vev_ask_hist": ask_hist}

        od = state.order_depths[product]
        bids = sorted(od.buy_orders, reverse=True)
        asks = sorted(od.sell_orders)
        best_bid = bids[0] if bids else (bid_hist[-1] if bid_hist else None)
        best_ask = asks[0] if asks else (ask_hist[-1] if ask_hist else None)

        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        if len(bid_hist) > sma_window:
            bid_hist.pop(0)
        if len(ask_hist) > sma_window:
            ask_hist.pop(0)

        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, {"vev_bid_hist": bid_hist, "vev_ask_hist": ask_hist}

        fair = (sum(bid_hist) + sum(ask_hist)) / (2.0 * sma_window)
        pos = state.position.get(product, 0)
        buy_cap = pos_lim - pos
        sell_cap = pos_lim + pos

        for ask in asks:
            if ask <= fair - 1 and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                result.append(Order(product, ask, qty))
                buy_cap -= qty
                break
        for bid in bids:
            if bid >= fair + 1 and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                result.append(Order(product, bid, -qty))
                sell_cap -= qty
                break

        pb = next((p for p in bids if p + 1 <= fair), None)
        pa = next((p for p in asks if p - 1 >= fair), None)
        if pb is None and best_bid is not None and best_bid + 1 <= fair:
            pb = best_bid
        if pa is None and best_ask is not None and best_ask - 1 >= fair:
            pa = best_ask
        if pb is not None and buy_cap > 0:
            result.append(Order(product, pb + 1, min(quote_lim, buy_cap)))
        if pa is not None and sell_cap > 0:
            result.append(Order(product, pa - 1, -min(quote_lim, sell_cap)))

        return result, {"vev_bid_hist": bid_hist, "vev_ask_hist": ask_hist}

    # ------------------------------------------------------------------
    # VEV Vouchers — SMA fair value, passive make only
    # ------------------------------------------------------------------
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
