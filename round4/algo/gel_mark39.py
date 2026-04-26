from datamodel import OrderDepth, TradingState, Order
from typing import List
import json


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

EOD_START = 990_000
EOD_HARD  = 999_900


class Trader:
    def run(self, state: TradingState):
        result = {}
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        result['HYDROGEL_PACK'], hp_data = self.hydrogel(state, shared)

        trader_data = json.dumps(hp_data)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def hydrogel(self, state: TradingState, shared: dict):
        product = 'HYDROGEL_PACK'
        pos_lim = 200
        take_thresh = 10

        ema = shared.get('hp_ema')
        last_m38_ts = shared.get('last_m38_ts', state.timestamp)

        od = state.order_depths.get(product)
        if not od or not od.buy_orders or not od.sell_orders:
            return [], {'hp_ema': ema, 'last_m38_ts': last_m38_ts}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0

        # EMA kept as long-range drift anchor only — not used for quoting
        ema = mid if ema is None else 0.02 * mid + 0.98 * ema
        fair = mid  # quote around current mid, not lagging EMA

        # Track Mark 38 timing: size up when they're statistically due (median gap ~700ts)
        m38_now = [t for t in state.market_trades.get(product, [])
                   if t.buyer == 'Mark 38' or t.seller == 'Mark 38']
        if m38_now:
            last_m38_ts = state.timestamp
        gap = state.timestamp - last_m38_ts
        boost = 2 if gap >= 600 else 1
        quote_size = 6 * boost

        pos = state.position.get(product, 0)
        buy_cap = pos_lim - pos
        sell_cap = pos_lim + pos
        orders = []

        # EOD flattening: aggressively close position in the last 10k ticks
        ts = state.timestamp
        if ts >= EOD_START and pos != 0:
            urgency = (ts - EOD_START) / (EOD_HARD - EOD_START)
            close_thresh = round(10 * (1 - urgency))  # 10 → 0 as day ends
            if pos > 0:
                for bid in sorted(od.buy_orders, reverse=True):
                    if bid >= fair - close_thresh and sell_cap > 0:
                        qty = min(sell_cap, pos, od.buy_orders[bid])
                        orders.append(Order(product, bid, -qty))
                        sell_cap -= qty
                        pos -= qty
            else:
                for ask in sorted(od.sell_orders):
                    if ask <= fair + close_thresh and buy_cap > 0:
                        qty = min(buy_cap, -pos, abs(od.sell_orders[ask]))
                        orders.append(Order(product, ask, qty))
                        buy_cap -= qty
                        pos += qty

        # Aggressive take on obvious mispricings (vs current mid, not EMA)
        for ask in sorted(od.sell_orders):
            if ask <= fair - take_thresh and buy_cap > 0:
                qty = min(buy_cap, abs(od.sell_orders[ask]))
                orders.append(Order(product, ask, qty))
                buy_cap -= qty
        for bid in sorted(od.buy_orders, reverse=True):
            if bid >= fair + take_thresh and sell_cap > 0:
                qty = min(sell_cap, od.buy_orders[bid])
                orders.append(Order(product, bid, -qty))
                sell_cap -= qty

        # Passive quotes: sit at best bid/ask (replacing Mark 14) with inventory skew
        # 1 tick per 20 units (was 40) for faster mean-reversion
        skew = -round(pos / 20)
        bid_px = best_bid + skew
        ask_px = best_ask + skew
        if bid_px >= ask_px:
            bid_px = ask_px - 1

        if buy_cap > 0 and ts < EOD_START:
            orders.append(Order(product, bid_px, min(quote_size, buy_cap)))
        if sell_cap > 0 and ts < EOD_START:
            orders.append(Order(product, ask_px, -min(quote_size, sell_cap)))

        if m38_now:
            logger.print(f"t={ts} M38={len(m38_now)} gap={gap} fair={fair:.1f} pos={pos} bid={bid_px} ask={ask_px} boost={boost}")

        return orders, {'hp_ema': ema, 'last_m38_ts': last_m38_ts}
