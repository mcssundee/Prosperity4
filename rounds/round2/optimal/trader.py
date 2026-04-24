from datamodel import TradingState, Order
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

    def wall_mid(self, order_depth) -> float | None:
        """
        Frankfurt Hedgehogs' Wall Mid: use the lowest bid-side price (bid wall)
        and highest ask-side price (ask wall) — the deep liquidity makers.
        Much more stable than best-bid/ask midpoint.
        """
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())
        if not bids or not asks:
            return None
        bid_wall = bids[-1]   # lowest bid (deepest support)
        ask_wall = asks[-1]   # highest ask (deepest resistance)
        return (bid_wall + ask_wall) / 2.0

    def ash(self, state: TradingState, shared: dict):
        """
        ASH_COATED_OSMIUM: Wall Mid market making with full position limit usage.

        Improvements over baseline:
        - Wall Mid fair value (more stable than SMA of best bid/ask)
        - Active taking up to full pos limit (80) instead of 60
        - Passive quoting fills remaining capacity up to ±80
        - Inventory skew: widen on the heavy side to encourage mean reversion
        """
        product = "ASH_COATED_OSMIUM"
        result = []
        pos_lim = 80
        quote_lim = 10

        if product not in state.order_depths:
            return result, {}

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())
        best_bid = bids[0] if bids else None
        best_ask = asks[0] if asks else None

        fair = self.wall_mid(order_depth)
        if fair is None:
            return result, {}

        pos = state.position.get(product, 0)
        buy_qty = min(quote_lim, pos_lim - pos)
        sell_qty = min(quote_lim, pos_lim + pos)

        # Active taking: buy underpriced asks, sell overpriced bids
        # Relax threshold by 1 tick when skewed to flatten inventory faster
        buy_threshold = fair + (1 if pos < -15 else 0)
        sell_threshold = fair - (1 if pos > 15 else 0)

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

        # Passive making: step through book to find best level within fair value
        if buy_qty > 0 and pos < pos_lim:
            passive_bid = next((p for p in bids if p + 1 <= fair), None) or best_bid
            if passive_bid is not None:
                result.append(Order(product, passive_bid + 1, buy_qty))

        if sell_qty > 0 and pos > -pos_lim:
            passive_ask = next((p for p in asks if p - 1 >= fair), None) or best_ask
            if passive_ask is not None:
                result.append(Order(product, passive_ask - 1, -sell_qty))

        return result, {}

    def root(self, state: TradingState, shared: dict):
        """
        INTARIAN_PEPPER_ROOT: Aggressive sweep to full limit with earlier trigger.

        Improvements over baseline:
        - Sweep to full position limit (80) instead of 76
        - Earlier sweep trigger: timestamp 1000 instead of 2000
        - Tighter re-entry after exit (-20 instead of -25) to capture more rebounds
        - Informed trader detection: if a bot consistently trades at daily extremes,
          copy-trade it at full position (currently a placeholder — populate with
          observed trader IDs/patterns from round data)
        """
        product = "INTARIAN_PEPPER_ROOT"
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80
        first_ask = shared.get("first_ask")
        peak_price = shared.get("peak_price")
        exited = shared.get("exited", False)

        root_data = {"first_ask": first_ask, "peak_price": peak_price, "exited": exited}

        if product not in state.order_depths:
            return result, root_data

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        # Check for informed trader signal in market trades
        # If a trader consistently buys at lows/sells at highs in fixed lots,
        # copy-trade them at full position
        informed_buy = False
        informed_sell = False
        if product in state.market_trades:
            for trade in state.market_trades[product]:
                # Placeholder: replace "INFORMED_BOT_ID" with observed trader ID
                # e.g. if trade.buyer == "Olivia": informed_buy = True
                pass

        if informed_buy and pos < pos_lim:
            if best_ask is not None:
                result.append(Order(product, best_ask, pos_lim - pos))
            return result, root_data

        if informed_sell and pos > 0:
            if best_bid is not None:
                result.append(Order(product, best_bid, -pos))
            return result, root_data

        # Standard peak-tracking with trailing stop
        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
            peak_price = mid_price if peak_price is None else max(peak_price, mid_price)

            if not exited and mid_price < peak_price - 50:
                exited = True
            elif exited and mid_price > peak_price - 20:   # tightened from -25
                exited = False

            root_data = {"first_ask": first_ask, "peak_price": peak_price, "exited": exited}

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
            root_data["first_ask"] = first_ask

        # Sweep to full 80 (not 76); earlier trigger at timestamp 1000
        if pos < pos_lim and (best_ask <= first_ask + 2 or state.timestamp >= 1000):
            qty = min(pos_lim - pos, abs(order_depth.sell_orders.get(best_ask, 1)))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        elif pos < pos_lim:
            if best_bid is not None:
                result.append(Order(product, best_bid + 1, pos_lim - pos))

        return result, root_data
