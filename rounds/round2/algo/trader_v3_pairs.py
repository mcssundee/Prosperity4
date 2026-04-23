from utils.datamodel import TradingState, Order
import json
import math


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        result = {}
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        ash_orders = self.trade_pair(state, shared, 'ASH_COATED_OSMIUM')
        root_orders = self.trade_pair(state, shared, 'INTARIAN_PEPPER_ROOT')

        result['ASH_COATED_OSMIUM'] = ash_orders
        result['INTARIAN_PEPPER_ROOT'] = root_orders

        price_hist = shared.get("price_hist", {})
        ash_mid = None
        root_mid = None

        if 'ASH_COATED_OSMIUM' in state.order_depths:
            depth = state.order_depths['ASH_COATED_OSMIUM']
            if depth.buy_orders and depth.sell_orders:
                ash_mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
                if 'ASH_COATED_OSMIUM' not in price_hist:
                    price_hist['ASH_COATED_OSMIUM'] = []
                price_hist['ASH_COATED_OSMIUM'].append(ash_mid)
                if len(price_hist['ASH_COATED_OSMIUM']) > 20:
                    price_hist['ASH_COATED_OSMIUM'].pop(0)

        if 'INTARIAN_PEPPER_ROOT' in state.order_depths:
            depth = state.order_depths['INTARIAN_PEPPER_ROOT']
            if depth.buy_orders and depth.sell_orders:
                root_mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0
                if 'INTARIAN_PEPPER_ROOT' not in price_hist:
                    price_hist['INTARIAN_PEPPER_ROOT'] = []
                price_hist['INTARIAN_PEPPER_ROOT'].append(root_mid)
                if len(price_hist['INTARIAN_PEPPER_ROOT']) > 20:
                    price_hist['INTARIAN_PEPPER_ROOT'].pop(0)

        traderData = json.dumps({"price_hist": price_hist})
        return result, conversions, traderData

    def trade_pair(self, state: TradingState, shared: dict, product: str):
        """Simple paired trade: buy underperformer, sell overperformer based on relative price levels."""
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 60

        if product not in state.order_depths:
            return result

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        if best_bid is None or best_ask is None:
            return result

        mid_price = (best_bid + best_ask) / 2.0

        price_hist = shared.get("price_hist", {}).get(product, [])
        if len(price_hist) < 20:
            return result

        mean_price = sum(price_hist) / len(price_hist)
        variance = sum((x - mean_price) ** 2 for x in price_hist) / len(price_hist)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0

        z_score = (mid_price - mean_price) / std_dev if std_dev > 0 else 0

        if z_score < -1.5 and pos < pos_lim:
            qty = min(20, pos_lim - pos)
            result.append(Order(product, best_ask, qty))
        elif z_score > 1.5 and pos > -pos_lim:
            qty = min(20, pos_lim + pos)
            result.append(Order(product, best_bid, -qty))
        elif -0.3 < z_score < 0.3 and pos != 0:
            result.append(Order(product, best_bid if pos > 0 else best_ask, -pos))

        return result
