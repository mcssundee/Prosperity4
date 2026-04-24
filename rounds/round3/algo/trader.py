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


def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _bs_call(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 1e-9 or sigma <= 1e-9:
        return max(S - K, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def _implied_vol(S: float, K: float, T: float, price: float):
    if T <= 1e-9:
        return None
    intrinsic = max(S - K, 0.0)
    if price <= intrinsic + 1e-9:
        return None
    lo, hi = 1e-6, 5.0
    if _bs_call(S, K, T, hi) < price:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if _bs_call(S, K, T, mid) > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-7:
            break
    return (lo + hi) / 2.0


VOUCHER_STRIKES = {
    'VEV_4000': 4000, 'VEV_4500': 4500,
    'VEV_5000': 5000, 'VEV_5100': 5100,
    'VEV_5200': 5200, 'VEV_5300': 5300,
    'VEV_5400': 5400, 'VEV_5500': 5500,
}

# (position_limit, passive_quote_qty)
VOUCHER_CFG = {
    'VEV_4000': (300, 5), 'VEV_4500': (300, 5),
    'VEV_5000': (300, 8), 'VEV_5100': (300, 8),
    'VEV_5200': (200, 5), 'VEV_5300': (200, 5),
    'VEV_5400': (100, 3), 'VEV_5500': (100, 3),
}

# Strikes used to calibrate the rolling IV (excludes deep ITM where IV is undefined)
IV_SYMS = ('VEV_5000', 'VEV_5100', 'VEV_5200', 'VEV_5300', 'VEV_5400', 'VEV_5500')

# TTE (days) at the START of round 3 live submission.
# Vouchers issued at round 1 with 7-day expiry; round 3 = 5 days remaining.
TTE_START = 5.0


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
    # HYDROGEL_PACK — mean-reversion MM around 10000
    # ------------------------------------------------------------------
    def hydrogel(self, state: TradingState, shared: dict):
        product = 'HYDROGEL_PACK'
        result = []
        pos_lim = 200
        quote_lim = 15
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
    # VELVETFRUIT_EXTRACT — SMA-5 market maker
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
    # VEV Vouchers — BS fair value using rolling mean IV
    # ------------------------------------------------------------------
    def vev_options(self, state: TradingState, shared: dict):
        result = defaultdict(list)
        opt = shared.get("vev_opt", {})
        iv_buf = opt.get("iv_buf", [])  # rolling 10-tick buffer of cross-sectional mean IV

        # Get VEV spot mid
        vev_od = state.order_depths.get('VELVETFRUIT_EXTRACT')
        if not vev_od or not vev_od.buy_orders or not vev_od.sell_orders:
            return result, {"vev_opt": opt}
        S = (max(vev_od.buy_orders) + min(vev_od.sell_orders)) / 2.0

        # TTE: starts at TTE_START days, decreases within the day.
        # Each day spans timestamps 0..999900 (10 000 ticks × 100 spacing).
        tte_days = max(TTE_START - state.timestamp / 1_000_000.0, 0.001)
        T = tte_days / 365.0

        # Calibrate rolling IV from near-ATM options
        ivs = []
        for sym in IV_SYMS:
            if sym not in state.order_depths:
                continue
            od = state.order_depths[sym]
            if not od.buy_orders or not od.sell_orders:
                continue
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
            iv = _implied_vol(S, VOUCHER_STRIKES[sym], T, mid)
            if iv is not None:
                ivs.append(iv)

        if ivs:
            iv_buf.append(sum(ivs) / len(ivs))
            if len(iv_buf) > 10:
                iv_buf.pop(0)
        opt["iv_buf"] = iv_buf

        if not iv_buf:
            return result, {"vev_opt": opt}

        mean_iv = sum(iv_buf) / len(iv_buf)

        # Quote every tradeable strike using BS fair
        for sym, (pos_lim, quote_qty) in VOUCHER_CFG.items():
            if sym not in state.order_depths:
                continue
            od = state.order_depths[sym]
            if not od.buy_orders or not od.sell_orders:
                continue

            K = VOUCHER_STRIKES[sym]
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            fair = _bs_call(S, K, T, mean_iv)
            fair_int = round(fair)

            pos = state.position.get(sym, 0)
            buy_cap = pos_lim - pos
            sell_cap = pos_lim + pos

            # Aggressive take when market is on the wrong side of fair
            if best_ask < fair and buy_cap > 0:
                qty = min(abs(od.sell_orders[best_ask]), buy_cap, quote_qty * 2)
                result[sym].append(Order(sym, best_ask, qty))
                buy_cap -= qty
            if best_bid > fair and sell_cap > 0:
                qty = min(od.buy_orders[best_bid], sell_cap, quote_qty * 2)
                result[sym].append(Order(sym, best_bid, -qty))
                sell_cap -= qty

            # Passive make 1 tick around BS fair
            if buy_cap > 0:
                result[sym].append(Order(sym, fair_int - 1, min(quote_qty, buy_cap)))
            if sell_cap > 0:
                result[sym].append(Order(sym, fair_int + 1, -min(quote_qty, sell_cap)))

        return result, {"vev_opt": opt}
