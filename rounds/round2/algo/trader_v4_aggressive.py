from utils.datamodel import TradingState, Order
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

        result['ASH_COATED_OSMIUM'] = self.ash_aggressive(state, shared)[0]
        ash_data = self.ash_aggressive(state, shared)[1]
        result['INTARIAN_PEPPER_ROOT'] = self.root_aggressive(state, shared)[0]
        root_data = self.root_aggressive(state, shared)[1]

        traderData = json.dumps({**ash_data, **root_data})
        return dict(result), conversions, traderData

    def ash_aggressive(self, state: TradingState, shared: dict):
        """ASH: More aggressive positioning and faster fills."""
        product = 'ASH_COATED_OSMIUM'
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80

        bid_hist = shared.get("bid_hist", [])
        ask_hist = shared.get("ask_hist", [])
        sma_window = 5

        if 'ASH_COATED_OSMIUM' not in state.order_depths:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}

        order_depth = state.order_depths['ASH_COATED_OSMIUM']
        bids = sorted(order_depth.buy_orders, reverse=True)
        asks = sorted(order_depth.sell_orders)
        curr_best_bid = bids[0] if len(bids) >= 1 else None
        curr_best_ask = asks[0] if len(asks) >= 1 else None

        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)

        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        if len(bid_hist) > sma_window:
            bid_hist.pop(0)
        if len(ask_hist) > sma_window:
            ask_hist.pop(0)

        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}

        bid_sma = sum(bid_hist) / sma_window
        ask_sma = sum(ask_hist) / sma_window
        fair_value = (bid_sma + ask_sma) / 2.0

        buy_qty = 15
        sell_qty = 15

        if fair_value is not None:
            buy_threshold = fair_value + (1 if pos < -10 else 0)
            sell_threshold = fair_value - (1 if pos > 10 else 0)

            for ask_px in asks:
                if ask_px <= buy_threshold and buy_qty != 0 and pos <= 50:
                    result.append(Order('ASH_COATED_OSMIUM', ask_px, buy_qty))
                    buy_qty = 0
                    break

            for bid_px in bids:
                if bid_px >= sell_threshold and sell_qty != 0 and pos >= -50:
                    result.append(Order('ASH_COATED_OSMIUM', bid_px, -sell_qty))
                    sell_qty = 0
                    break

        passive_bid = next((p for p in bids if p + 1 <= fair_value), None) if fair_value is not None else best_bid
        if passive_bid is None and best_bid is not None:
            passive_bid = best_bid
        passive_ask = next((p for p in asks if p - 1 >= fair_value), None) if fair_value is not None else best_ask
        if passive_ask is None and best_ask is not None:
            passive_ask = best_ask

        if passive_bid is not None and buy_qty != 0 and pos < pos_lim:
            result.append(Order('ASH_COATED_OSMIUM', passive_bid + 1, buy_qty))
        if passive_ask is not None and sell_qty != 0 and pos > -pos_lim:
            result.append(Order('ASH_COATED_OSMIUM', passive_ask - 1, -sell_qty))

        return result, {"bid_hist": bid_hist, "ask_hist": ask_hist}

    def root_aggressive(self, state: TradingState, shared: dict):
        """ROOT: Sweep to higher positions faster, more aggressive re-entry."""
        product = 'INTARIAN_PEPPER_ROOT'
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

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
            if peak_price is None:
                peak_price = mid_price
            else:
                peak_price = max(peak_price, mid_price)

            if not exited and mid_price < peak_price - 40:
                exited = True
            elif exited and mid_price > peak_price - 15:
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

        if pos < 78 and (best_ask <= first_ask + 3 or state.timestamp >= 1500):
            qty = min(78 - pos, abs(order_depth.sell_orders.get(best_ask, 1)))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        elif pos < pos_lim:
            if best_bid is not None:
                result.append(Order(product, best_bid + 1, pos_lim - pos))

        return result, root_data
