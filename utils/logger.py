import json
from utils.datamodel import TradingState


def flush(state: TradingState, orders: dict, conversions: int, trader_data: str):
    """Log state for the Prosperity visualizer (compatible with jmerle's visualizer)."""
    log_entry = {
        "sandboxLog": "",
        "lambdaLog": "",
        "timestamp": state.timestamp,
    }
    print(json.dumps(log_entry))
