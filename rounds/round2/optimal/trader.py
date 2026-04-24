from datamodel import TradingState, Order
from typing import Optional
import json
from collections import defaultdict


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        result = defaultdict(list)
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        result["ASH_COATED_OSMIUM"], ash_data = self.ash(state, shared)
        result["INTARIAN_PEPPER_ROOT"], root_data = self.root(state, shared)

        traderData = json.dumps({**ash_data, **root_data})
        return dict(result), conversions, traderData

    # ── helpers ──────────────────────────────────────────────────────────────

    def vwap_mid(self, order_depth) -> Optional[float]:
        """Volume-weighted mid across full book — denoises transient best-bid/ask spikes."""
        bid_num = sum(p * v for p, v in order_depth.buy_orders.items())
        bid_vol = sum(order_depth.buy_orders.values())
        ask_num = sum(p * abs(v) for p, v in order_depth.sell_orders.items())
        ask_vol = sum(abs(v) for v in order_depth.sell_orders.values())
        if bid_vol == 0 or ask_vol == 0:
            return None
        return (bid_num / bid_vol + ask_num / ask_vol) / 2.0

    def imbalance(self, order_depth) -> float:
        """Order-book imbalance: +1 = all bids, -1 = all asks."""
        bid_vol = sum(order_depth.buy_orders.values())
        ask_vol = sum(abs(v) for v in order_depth.sell_orders.values())
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    # ── ASH_COATED_OSMIUM ────────────────────────────────────────────────────

    def ash(self, state: TradingState, shared: dict):
        """
        Drift-adjusted mean reversion with:
        - Rolling 10-period median mid-price as fair value (robust to outliers)
        - Inventory-skewed internal pivot (lean into spread to manage risk)
        - 12-tick deviation sniper (capture large mispricings immediately)
        - Passive MM in 15-unit chunks for standard flow
        - Order-flow imbalance signal to bias quote placement
        """
        product = "ASH_COATED_OSMIUM"
        result = []
        pos_lim = 80
        median_window = 10
        snipe_threshold = 12
        passive_qty = 15

        mid_hist = shared.get("ash_mid_hist", [])

        if product not in state.order_depths:
            return result, {"ash_mid_hist": mid_hist}

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())
        best_bid = bids[0] if bids else None
        best_ask = asks[0] if asks else None

        # VWAP mid; fall back to simple mid if book is one-sided
        mid = self.vwap_mid(order_depth)
        if mid is None and best_bid and best_ask:
            mid = (best_bid + best_ask) / 2.0
        if mid is None and mid_hist:
            mid = mid_hist[-1]      # backfill from history during empty book
        if mid is None:
            return result, {"ash_mid_hist": mid_hist}

        mid_hist.append(mid)
        if len(mid_hist) > median_window:
            mid_hist.pop(0)

        # Median-based fair value (robust to outliers)
        sorted_hist = sorted(mid_hist)
        n = len(sorted_hist)
        fair = (sorted_hist[n // 2] + sorted_hist[(n - 1) // 2]) / 2.0

        pos = state.position.get(product, 0)

        # Inventory-skewed pivot: lean against position to encourage reversion
        # Long → pivot below fair (makes sells more competitive)
        # Short → pivot above fair (makes buys more competitive)
        pivot = fair - pos * 0.1

        imb = self.imbalance(order_depth)

        # ── Sniper: take any price > 12 ticks from pivot ──
        if best_ask is not None and best_ask < pivot - snipe_threshold and pos < pos_lim:
            qty = min(pos_lim - pos, sum(abs(v) for v in order_depth.sell_orders.values()))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
                pos += qty

        if best_bid is not None and best_bid > pivot + snipe_threshold and pos > -pos_lim:
            qty = min(pos_lim + pos, sum(order_depth.buy_orders.values()))
            if qty > 0:
                result.append(Order(product, best_bid, -qty))
                pos -= qty

        # ── Standard active taking near fair value ──
        buy_qty = min(passive_qty, pos_lim - pos)
        sell_qty = min(passive_qty, pos_lim + pos)

        buy_threshold = pivot + (1 if pos < -15 else 0)
        sell_threshold = pivot - (1 if pos > 15 else 0)

        for ask_px in asks:
            if ask_px <= buy_threshold and buy_qty > 0 and pos < pos_lim:
                qty = min(buy_qty, abs(order_depth.sell_orders[ask_px]))
                result.append(Order(product, ask_px, qty))
                buy_qty -= qty
                pos += qty
                break

        for bid_px in bids:
            if bid_px >= sell_threshold and sell_qty > 0 and pos > -pos_lim:
                qty = min(sell_qty, order_depth.buy_orders[bid_px])
                result.append(Order(product, bid_px, -qty))
                sell_qty -= qty
                pos -= qty
                break

        # ── Passive MM: bias placement using imbalance signal ──
        # Imbalance > 0 (more bids) → expect slight downward reversion → lean ask-side
        imb_adj = round(imb * 2)    # small tick nudge based on imbalance

        if buy_qty > 0 and pos < pos_lim and best_bid is not None:
            passive_bid = next((p for p in bids if p + 1 <= pivot), None) or best_bid
            result.append(Order(product, passive_bid + 1 - imb_adj, buy_qty))

        if sell_qty > 0 and pos > -pos_lim and best_ask is not None:
            passive_ask = next((p for p in asks if p - 1 >= pivot), None) or best_ask
            result.append(Order(product, passive_ask - 1 - imb_adj, -sell_qty))

        return result, {"ash_mid_hist": mid_hist}

    # ── INTARIAN_PEPPER_ROOT ─────────────────────────────────────────────────

    def root(self, state: TradingState, shared: dict):
        """
        Time-phase momentum strategy:

        Phase 1 — Early game (timestamp < 1500):
          Aggressive accumulation: sweep available asks at market price only.
          No overpaying — buy at ask prices already in the book.

        Phase 2 — Mid game (1500 ≤ timestamp < 9500):
          Standard sweep: buy at first_ask + 2 tolerance or after ts 2000.
          Trailing stop exits if mid drops 50 below peak; re-enters at peak - 20.

        Phase 3 — End game (timestamp ≥ 9500):
          Hold position; unrealized PnL is locked in at final price.
          Do not force-exit — the backtester marks open positions at close price.
        """
        product = "INTARIAN_PEPPER_ROOT"
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80
        ts = state.timestamp

        first_ask = shared.get("root_first_ask")
        peak_price = shared.get("root_peak_price")
        exited = shared.get("root_exited", False)

        root_data = {
            "root_first_ask": first_ask,
            "root_peak_price": peak_price,
            "root_exited": exited,
        }

        if product not in state.order_depths:
            return result, root_data

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        if best_bid is not None and best_ask is not None:
            mid = (best_bid + best_ask) / 2.0
            peak_price = mid if peak_price is None else max(peak_price, mid)
            if not exited and mid < peak_price - 50:
                exited = True
            elif exited and mid > peak_price - 20:
                exited = False
            root_data = {"root_first_ask": first_ask, "root_peak_price": peak_price, "root_exited": exited}

        # Trailing stop: sell down on exit signal
        if exited:
            if best_bid is not None and pos > 0:
                sell_qty = min(order_depth.buy_orders.get(best_bid, pos), pos)
                if sell_qty > 0:
                    result.append(Order(product, best_bid, -sell_qty))
            return result, root_data

        if best_ask is None:
            return result, root_data

        if first_ask is None:
            first_ask = best_ask
            root_data["root_first_ask"] = first_ask

        # Phase 1: sweep available asks at market price, no premium
        if ts < 1500 and pos < pos_lim:
            remaining = pos_lim - pos
            for ask_px in sorted(order_depth.sell_orders.keys()):
                if remaining <= 0:
                    break
                qty = min(remaining, abs(order_depth.sell_orders[ask_px]))
                result.append(Order(product, ask_px, qty))
                remaining -= qty
            # Passive penny-jump to fill any remaining gap
            if remaining > 0 and best_bid is not None:
                result.append(Order(product, best_bid + 1, remaining))
            return result, root_data

        # Phase 2: standard sweep — full pos_lim (not 76)
        if pos < pos_lim and (best_ask <= first_ask + 2 or ts >= 2000):
            qty = min(pos_lim - pos, abs(order_depth.sell_orders.get(best_ask, 1)))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        elif pos < pos_lim and best_bid is not None:
            result.append(Order(product, best_bid + 1, pos_lim - pos))

        return result, root_data
