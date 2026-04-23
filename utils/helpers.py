# Common math and utility functions

def mid_price(buy_orders, sell_orders):
    """Calculate mid price from order book."""
    if not buy_orders or not sell_orders:
        return None
    best_buy = max(buy_orders.keys()) if buy_orders else None
    best_ask = min(sell_orders.keys()) if sell_orders else None
    if best_buy and best_ask:
        return (best_buy + best_ask) / 2
    return best_buy or best_ask

def spread(buy_orders, sell_orders):
    """Calculate bid-ask spread."""
    if not buy_orders or not sell_orders:
        return None
    best_buy = max(buy_orders.keys())
    best_ask = min(sell_orders.keys())
    return best_ask - best_buy

def calculate_pnl(positions, prices):
    """Calculate PnL given positions and current prices."""
    pnl = 0
    for symbol, quantity in positions.items():
        price = prices.get(symbol, 0)
        pnl += quantity * price
    return pnl
