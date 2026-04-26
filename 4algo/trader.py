from utils.datamodel import TradingState, Order


class Trader:
    def __init__(self):
        self.position = {}

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        """Main trading strategy for this round."""
        result = {}

        # TODO: Implement strategy for this round

        return result, 0, state.traderData
