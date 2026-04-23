# Copy official Prosperity datamodel here
# See: https://prosperity.imc.com/
# This file should be copied from the competition portal

class OrderDepth:
    def __init__(self):
        self.buy_orders = {}
        self.sell_orders = {}

class Trade:
    def __init__(self, symbol, price, quantity):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.timestamp = None

class State:
    def __init__(self):
        self.timestamp = 0
        self.listings = {}
        self.order_depths = {}
        self.own_trades = {}
        self.market_trades = {}
        self.position = {}
        self.observations = {}

class Order:
    def __init__(self, symbol, quantity, price):
        self.symbol = symbol
        self.quantity = quantity
        self.price = price

class OrderStatus:
    def __init__(self):
        self.orders = {}
        self.submissions = []
