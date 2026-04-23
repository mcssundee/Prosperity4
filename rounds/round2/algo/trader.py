from utils.datamodel import TradingState, Order

POSITION_LIMIT = 80


class Trader:
    def bid(self):
        return 10

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        result = {}

        for symbol, depth in state.order_depths.items():
            orders = []
            pos = state.position.get(symbol, 0)

            if depth.buy_orders:
                bid = max(depth.buy_orders)
                if pos < POSITION_LIMIT:
                    orders.append(Order(symbol, bid, 10))

            if depth.sell_orders:
                ask = min(depth.sell_orders)
                if pos > -POSITION_LIMIT:
                    orders.append(Order(symbol, ask, -10))

            result[symbol] = orders

        return result, 0, state.traderData
