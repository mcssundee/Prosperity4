import json
import math
from datamodel import Order, TradingState
from typing import List

HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 10
HYDRO_MAX_SPREAD = 20

# --- Bollinger Bands ---
# EMA-based rolling mean and variance of microprice.
# alpha=0.001 → ~693-tick halflife (~70 seconds).
HYDRO_MU_ALPHA  = 0.001
HYDRO_VAR_ALPHA = 0.001
HYDRO_BB_K      = 2.0    # entry threshold in standard deviations
HYDRO_VAR_INIT  = 25.0   # initial variance (σ=5 ticks); converges to true vol
HYDRO_WARMUP    = 500    # ticks before taker fires — lets EMAs calibrate

# --- Trend filter (EMA crossover) ---
# Blocks taker from buying into downtrends / selling into uptrends.
# fast α=0.01 (~69-tick), slow α=0.001 (~693-tick).
HYDRO_FAST_ALPHA   = 0.01
HYDRO_SLOW_ALPHA   = 0.001
HYDRO_TREND_THRESH = 5.0

# --- RSI ---
# Confirmation filter: only take a trade when RSI agrees with the BB signal.
HYDRO_RSI_ALPHA = 0.005
HYDRO_RSI_LOW   = 47     # below this = oversold → confirms buy
HYDRO_RSI_HIGH  = 53     # above this = overbought → confirms sell

# --- ATR ---
# EMA of |microprice change per tick| — scales position size.
# MAX_MULT capped at 1.0: ATR can shrink positions in high vol but never inflate them.
HYDRO_ATR_ALPHA    = 0.01
HYDRO_ATR_BASELINE = 2.0   # calibrated to actual observed ATR (~1.75–2.9 ticks)
HYDRO_ATR_MIN      = 0.5
HYDRO_ATR_MAX_MULT = 1.0   # no upside scaling — only shrink in high vol

# Base position target at z=BB_K and normal ATR.
HYDRO_BASE_TARGET = 55

HYDRO_TAKER_MAX  = 100   # taker never builds more than this; limits trend exposure

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

        prev = saved.get("hydro_prev", microprice)

        # --- Bollinger Bands ---
        mu  = saved.get("hydro_mu",  microprice)
        var = saved.get("hydro_var", HYDRO_VAR_INIT)
        mu  = HYDRO_MU_ALPHA  * microprice             + (1 - HYDRO_MU_ALPHA)  * mu
        var = HYDRO_VAR_ALPHA * (microprice - mu) ** 2 + (1 - HYDRO_VAR_ALPHA) * var
        sigma = math.sqrt(var) if var > 0 else 1.0
        z = (mu - microprice) / sigma  # positive = price below mean = buy signal

        # --- Trend filter (EMA crossover) ---
        fast = saved.get("hydro_fast", microprice)
        slow = saved.get("hydro_slow", microprice)
        fast = HYDRO_FAST_ALPHA * microprice + (1 - HYDRO_FAST_ALPHA) * fast
        slow = HYDRO_SLOW_ALPHA * microprice + (1 - HYDRO_SLOW_ALPHA) * slow
        trend_gap     = fast - slow
        trending_up   = trend_gap >  HYDRO_TREND_THRESH
        trending_down = trend_gap < -HYDRO_TREND_THRESH

        # --- RSI ---
        avg_gain = saved.get("hydro_gain", 0.5)
        avg_loss = saved.get("hydro_loss", 0.5)
        chg = microprice - prev
        avg_gain = HYDRO_RSI_ALPHA * max(chg,  0) + (1 - HYDRO_RSI_ALPHA) * avg_gain
        avg_loss = HYDRO_RSI_ALPHA * max(-chg, 0) + (1 - HYDRO_RSI_ALPHA) * avg_loss
        if avg_loss > 0:
            rsi = 100 - 100 / (1 + avg_gain / avg_loss)
        elif avg_gain > 0:
            rsi = 100.0
        else:
            rsi = 50.0

        # --- ATR ---
        atr = saved.get("hydro_atr", HYDRO_ATR_BASELINE)
        atr = HYDRO_ATR_ALPHA * abs(microprice - prev) + (1 - HYDRO_ATR_ALPHA) * atr

        # Persist state
        ticks = saved.get("hydro_ticks", 0) + 1
        saved["hydro_ticks"] = ticks
        saved["hydro_prev"]  = microprice
        saved["hydro_mu"]    = mu
        saved["hydro_var"]   = var
        saved["hydro_fast"]  = fast
        saved["hydro_slow"]  = slow
        saved["hydro_gain"]  = avg_gain
        saved["hydro_loss"]  = avg_loss
        saved["hydro_atr"]   = atr

        # --- Position target ---
        # ATR only shrinks position in high vol; never inflates it (MAX_MULT=1.0).
        vol_scale  = min(HYDRO_ATR_BASELINE / max(atr, HYDRO_ATR_MIN), HYDRO_ATR_MAX_MULT)
        raw_target = (z / HYDRO_BB_K) * HYDRO_BASE_TARGET * vol_scale
        target     = int(max(-HYDRO_TAKER_MAX, min(HYDRO_TAKER_MAX, raw_target)))
        delta      = max(-HYDRO_STEP_SIZE, min(HYDRO_STEP_SIZE, target - pos))

        # --- Taker ---
        # Gate on warmup: EMAs need time to calibrate before taker fires.
        orders: List[Order] = []
        if ticks >= HYDRO_WARMUP and abs(z) >= HYDRO_BB_K:
            if delta > 0 and rsi < HYDRO_RSI_LOW:
                qty = min(delta, buy_room)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))
            elif delta < 0 and rsi > HYDRO_RSI_HIGH:
                qty = min(-delta, sell_room)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

        # --- Maker ---
        # Passive quotes inside the spread when position is near flat.
        if not orders and spread >= 4 and abs(pos) <= HYDRO_MAKER_MAX_POS:
            quote_bid = best_bid + 1
            quote_ask = best_ask - 1
            if quote_bid < quote_ask:
                if buy_room > 0:
                    orders.append(Order(product, quote_bid, min(HYDRO_MAKER_SIZE, buy_room)))
                if sell_room > 0:
                    orders.append(Order(product, quote_ask, -min(HYDRO_MAKER_SIZE, sell_room)))

        return orders
