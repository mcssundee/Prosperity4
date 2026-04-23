# Base strategy classes and utilities

class BaseStrategy:
    """Base class for all trading strategies."""

    def __init__(self):
        self.position = {}
        self.pnl = 0

    def on_state(self, state):
        """Process market state and return list of orders."""
        raise NotImplementedError

    def update_position(self, symbol, quantity):
        """Update position in a symbol."""
        self.position[symbol] = self.position.get(symbol, 0) + quantity

    def get_position(self, symbol):
        """Get current position in a symbol."""
        return self.position.get(symbol, 0)
