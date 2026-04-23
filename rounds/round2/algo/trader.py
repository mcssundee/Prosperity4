from utils.datamodel import TradingState, Order

POSITION_LIMIT = 50


class Trader:
    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        """Immediate close strategy: buy and sell each tick to lock in spread."""
        result = {}

        for symbol, depth in state.order_depths.items():
            if not depth.buy_orders or not depth.sell_orders:
                continue

            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            orders = []

            qty = 1
            orders.append(Order(symbol, int(best_ask), qty))
            orders.append(Order(symbol, int(best_bid), -qty))

            result[symbol] = orders

        return result, 0, state.traderData
