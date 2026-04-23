from utils.datamodel import TradingState, Order
import json
from collections import defaultdict
import math


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

        result['ASH_COATED_OSMIUM'] = self.ash_bollinger(state, shared)[0]
        ash_data = self.ash_bollinger(state, shared)[1]
        result['INTARIAN_PEPPER_ROOT'] = self.root_momentum(state, shared)[0]
        root_data = self.root_momentum(state, shared)[1]

        traderData = json.dumps({**ash_data, **root_data})
        return dict(result), conversions, traderData

    def ash_bollinger(self, state: TradingState, shared: dict):
        """ASH: Mean-reversion with Bollinger bands (Strategy 2)."""
        product = 'ASH_COATED_OSMIUM'
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80

        mid_hist = shared.get("ash_mid_hist", [])
        entry_price = shared.get("ash_entry_price")
        position_age = shared.get("ash_position_age", 0)

        if product not in state.order_depths:
            return result, {"ash_mid_hist": mid_hist, "ash_entry_price": entry_price, "ash_position_age": position_age}

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        if best_bid is None or best_ask is None:
            return result, {"ash_mid_hist": mid_hist, "ash_entry_price": entry_price, "ash_position_age": position_age}

        mid_price = (best_bid + best_ask) / 2.0
        mid_hist.append(mid_price)
        if len(mid_hist) > 10:
            mid_hist.pop(0)

        position_age += 1

        data = {"ash_mid_hist": mid_hist, "ash_entry_price": entry_price, "ash_position_age": position_age}

        if len(mid_hist) < 10:
            return result, data

        mean = sum(mid_hist) / len(mid_hist)
        variance = sum((x - mean) ** 2 for x in mid_hist) / len(mid_hist)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0

        upper_band = mean + 2.0 * std_dev
        lower_band = mean - 2.0 * std_dev

        buy_qty = min(15, pos_lim - pos) if pos < pos_lim else 0
        sell_qty = min(15, pos_lim + pos) if pos > -pos_lim else 0

        if pos > 0 and position_age > 40:
            result.append(Order(product, best_bid, -pos))
            data["ash_entry_price"] = None
            data["ash_position_age"] = 0
        elif pos > 0 and mid_price > mean - 0.75 * std_dev:
            result.append(Order(product, best_bid, -pos))
            data["ash_entry_price"] = None
            data["ash_position_age"] = 0
        elif pos < 0 and position_age > 40:
            result.append(Order(product, best_ask, -pos))
            data["ash_entry_price"] = None
            data["ash_position_age"] = 0
        elif pos < 0 and mid_price < mean + 0.75 * std_dev:
            result.append(Order(product, best_ask, -pos))
            data["ash_entry_price"] = None
            data["ash_position_age"] = 0
        elif mid_price < lower_band - 1 and buy_qty > 0 and pos == 0:
            result.append(Order(product, best_ask, buy_qty))
            data["ash_entry_price"] = best_ask
            data["ash_position_age"] = 1
        elif mid_price > upper_band + 1 and sell_qty > 0 and pos == 0:
            result.append(Order(product, best_bid, -sell_qty))
            data["ash_entry_price"] = best_bid
            data["ash_position_age"] = 1

        return result, data

    def root_momentum(self, state: TradingState, shared: dict):
        """ROOT: Momentum following with EMA acceleration (Strategy 1)."""
        product = 'INTARIAN_PEPPER_ROOT'
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80

        mid_hist = shared.get("root_mid_hist", [])
        entry_price = shared.get("root_entry_price")
        pyramid_level = shared.get("root_pyramid_level", 0)

        if product not in state.order_depths:
            return result, {"root_mid_hist": mid_hist, "root_entry_price": entry_price, "root_pyramid_level": pyramid_level}

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        if best_bid is None or best_ask is None:
            return result, {"root_mid_hist": mid_hist, "root_entry_price": entry_price, "root_pyramid_level": pyramid_level}

        mid_price = (best_bid + best_ask) / 2.0
        mid_hist.append(mid_price)
        if len(mid_hist) > 7:
            mid_hist.pop(0)

        data = {"root_mid_hist": mid_hist, "root_entry_price": entry_price, "root_pyramid_level": pyramid_level}

        if len(mid_hist) < 7:
            return result, data

        ema3 = sum(mid_hist[-3:]) / 3.0
        ema7 = sum(mid_hist) / 7.0
        momentum = ema3 - ema7

        if pos > 0 and momentum < -1:
            result.append(Order(product, best_bid, -pos))
            data["root_entry_price"] = None
            data["root_pyramid_level"] = 0
        elif pos < 0 and momentum > 1:
            result.append(Order(product, best_ask, -pos))
            data["root_entry_price"] = None
            data["root_pyramid_level"] = 0
        elif pos > 0 and mid_price < entry_price - 35:
            result.append(Order(product, best_bid, -pos))
            data["root_entry_price"] = None
            data["root_pyramid_level"] = 0
        elif pos < 0 and mid_price > entry_price + 35:
            result.append(Order(product, best_ask, -pos))
            data["root_entry_price"] = None
            data["root_pyramid_level"] = 0
        elif momentum > 0.5 and pos < 75:
            buy_qty = min(12, pos_lim - pos)
            if buy_qty > 0:
                result.append(Order(product, best_ask, buy_qty))
                if entry_price is None:
                    data["root_entry_price"] = best_ask
                data["root_pyramid_level"] = pyramid_level + 1
        elif momentum < -0.5 and pos > -75:
            sell_qty = min(12, pos_lim + pos)
            if sell_qty > 0:
                result.append(Order(product, best_bid, -sell_qty))
                if entry_price is None:
                    data["root_entry_price"] = best_bid
                data["root_pyramid_level"] = pyramid_level + 1

        return result, data
