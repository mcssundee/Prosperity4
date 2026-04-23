# Prosperity 4 Trader
# This file is the final submission for the algo section each round.
# Before submission, copy the developed strategy from rounds/roundX/algo/trader.py

from utils.datamodel import TradingState, Order


class Trader:
    def __init__(self):
        self.position = {}

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        """
        Main entry point for the trading algorithm.

        state: the current TradingState object from the competition
        returns: (orders, conversions, trader_data)
          - orders: dict[symbol, list[Order]] — orders keyed by product
          - conversions: int — number of conversions (set to 0 for rounds 1/2)
          - trader_data: str — arbitrary state to persist across ticks
        """
        result = {}

        # TODO: Implement trading strategy

        return result, 0, state.traderData
