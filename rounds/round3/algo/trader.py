from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json
import math
import os
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

# ------------------------------------------------------------------
# Black-Scholes helpers (pure stdlib, no scipy)
# ------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _bs_call(S: float, K: float, T: float, sigma: float) -> float:
    """European call price (r=0). T in years, sigma annualised."""
    if T <= 1e-9:
        return max(S - K, 0.0)
    if sigma <= 1e-9:
        return max(S - K, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return S * _norm_cdf(d1) - K * _norm_cdf(d2)


def _implied_vol(S: float, K: float, T: float, price: float):
    """Bisection IV search; returns None if ill-conditioned."""
    if T <= 1e-9:
        return None
    intrinsic = max(S - K, 0.0)
    if price <= intrinsic + 1e-9:
        return None
    lo, hi = 1e-6, 5.0
    if _bs_call(S, K, T, hi) < price:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _bs_call(S, K, T, mid) > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-7:
            break
    return (lo + hi) / 2.0


def _solve3x3(A: list, b: list):
    """Gaussian elimination for 3×3 system Ax=b. Returns x or None."""
    import copy
    M = [A[i][:] + [b[i]] for i in range(3)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(M[r][col]))
        M[col], M[pivot] = M[pivot], M[col]
        if abs(M[col][col]) < 1e-15:
            return None
        for row in range(col + 1, 3):
            f = M[row][col] / M[col][col]
            for j in range(col, 4):
                M[row][j] -= f * M[col][j]
    x = [0.0] * 3
    for i in range(2, -1, -1):
        x[i] = M[i][3]
        for j in range(i + 1, 3):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]
    return x


def _fit_quadratic(xs: list, ys: list):
    """Least-squares quadratic fit y = a*x^2 + b*x + c.
    Returns (a, b, c) or None if not enough data."""
    n = len(xs)
    if n < 3:
        return None
    s4 = s3 = s2 = s1 = s0 = sy2 = sy1 = sy0 = 0.0
    for x, y in zip(xs, ys):
        x2 = x * x
        s4 += x2 * x2
        s3 += x2 * x
        s2 += x2
        s1 += x
        s0 += 1.0
        sy2 += x2 * y
        sy1 += x * y
        sy0 += y
    A = [[s4, s3, s2], [s3, s2, s1], [s2, s1, s0]]
    b = [sy2, sy1, sy0]
    return _solve3x3(A, b)


# ------------------------------------------------------------------
# Voucher configuration
# ------------------------------------------------------------------
VOUCHER_STRIKES = {
    'VEV_4000': 4000, 'VEV_4500': 4500,
    'VEV_5000': 5000, 'VEV_5100': 5100,
    'VEV_5200': 5200, 'VEV_5300': 5300,
    'VEV_5400': 5400, 'VEV_5500': 5500,
    'VEV_6000': 6000, 'VEV_6500': 6500,
}
DEEP_ITM = {'VEV_4000', 'VEV_4500'}
DEEP_OTM = {'VEV_6000', 'VEV_6500'}
ACTIVE_STRIKES = {k for k in VOUCHER_STRIKES if k not in DEEP_ITM and k not in DEEP_OTM}

IV_WINDOW = 50        # rolling IV history per strike
OPT_POS_LIM = 50      # per-strike position cap
ITM_QUOTE = 5         # passive quote size for deep-ITM
# TTE at round-3 day-0 start:
#   - live submission: 5 days (no PROSPERITY4BT_DAY env var)
#   - historical data: 8 - day_num (set by backtester env)


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

        # Active take
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

        # Passive make
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

        # Active take
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

        # Passive make
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
    # VEV Vouchers — deep-ITM MM + vol-smile IV scalping (near ATM only)
    # ------------------------------------------------------------------
    def vev_options(self, state: TradingState, shared: dict):
        result = defaultdict(list)
        opt = shared.get("opt_data", {})

        # TTE: use backtester env variable if available, else assume live round-3 (TTE=5)
        bt_day = os.environ.get("PROSPERITY4BT_DAY")
        base_tte_days = (8.0 - int(bt_day)) if bt_day is not None else 5.0
        tte_days = max(base_tte_days - state.timestamp / 1_000_000, 0.01)
        tte_years = tte_days / 365.0

        # Get VEV spot mid
        spot = None
        if 'VELVETFRUIT_EXTRACT' in state.order_depths:
            od_s = state.order_depths['VELVETFRUIT_EXTRACT']
            if od_s.buy_orders and od_s.sell_orders:
                spot = (max(od_s.buy_orders) + min(od_s.sell_orders)) / 2.0

        # ---- Deep ITM: passive market making on mid ----
        itm_mid_hist = opt.get("itm_mid_hist", {})
        for sym in DEEP_ITM:
            if sym not in state.order_depths:
                continue
            od = state.order_depths[sym]
            bids = sorted(od.buy_orders, reverse=True)
            asks = sorted(od.sell_orders)
            if not bids or not asks:
                continue
            mid = (bids[0] + asks[0]) / 2.0
            hist = itm_mid_hist.get(sym, [])
            hist.append(mid)
            if len(hist) > 3:
                hist.pop(0)
            itm_mid_hist[sym] = hist
            fair = sum(hist) / len(hist)
            pos = state.position.get(sym, 0)
            buy_cap = 300 - pos
            sell_cap = 300 + pos
            fair_int = round(fair)
            if buy_cap > 0:
                result[sym].append(Order(sym, fair_int - 1, min(ITM_QUOTE, buy_cap)))
            if sell_cap > 0:
                result[sym].append(Order(sym, fair_int + 1, -min(ITM_QUOTE, sell_cap)))
        opt["itm_mid_hist"] = itm_mid_hist

        if spot is None:
            return result, {"opt_data": opt}

        # ---- Active strikes: vol smile IV scalping, active take only ----
        iv_hist = opt.get("iv_hist", {})
        current_ivs = {}
        moneynesses = {}

        for sym in ACTIVE_STRIKES:
            K = VOUCHER_STRIKES[sym]
            if sym not in state.order_depths:
                continue
            od = state.order_depths[sym]
            if not od.buy_orders or not od.sell_orders:
                continue
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
            iv = _implied_vol(spot, K, tte_years, mid)
            if iv is None:
                continue
            current_ivs[sym] = iv
            moneynesses[sym] = math.log(K / spot) / math.sqrt(tte_days)
            hist = iv_hist.get(sym, [])
            hist.append(iv)
            if len(hist) > IV_WINDOW:
                hist.pop(0)
            iv_hist[sym] = hist
        opt["iv_hist"] = iv_hist

        # Need at least 3 warmed-up strikes to fit a reliable smile
        ready_syms = [s for s in current_ivs if len(iv_hist.get(s, [])) >= 10]
        if len(ready_syms) < 3:
            return result, {"opt_data": opt}

        xs = [moneynesses[s] for s in ready_syms]
        ys = [current_ivs[s] for s in ready_syms]
        smile_params = _fit_quadratic(xs, ys)
        if smile_params is None:
            mean_iv = sum(ys) / len(ys)
            smile_params = (0.0, 0.0, mean_iv)
        a, b, c = smile_params

        for sym in ready_syms:
            K = VOUCHER_STRIKES[sym]
            m = moneynesses[sym]
            smile_iv = max(a * m * m + b * m + c, 0.01)
            fair_price = _bs_call(spot, K, tte_years, smile_iv)
            od = state.order_depths[sym]
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            pos = state.position.get(sym, 0)
            buy_cap = OPT_POS_LIM - pos
            sell_cap = OPT_POS_LIM + pos

            # Active take when option deviates significantly from smile fair price
            if best_ask < fair_price - SMILE_THRESH and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[best_ask]))
                if qty > 0:
                    result[sym].append(Order(sym, best_ask, qty))
            elif best_bid > fair_price + SMILE_THRESH and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[best_bid])
                if qty > 0:
                    result[sym].append(Order(sym, best_bid, -qty))

        return result, {"opt_data": opt}
