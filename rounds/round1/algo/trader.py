from utils.datamodel import TradingState, Order


class Trader:
    def __init__(self):
        self.position = {}

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        """Main trading strategy for round 1."""
        result = {}

        # TODO: Implement strategy for round 1

        return result, 0, state.traderData
