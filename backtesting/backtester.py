#!/usr/bin/env python3
# Backtesting framework for Prosperity strategies

import sys
import argparse

def run_backtest(round_num, trader_class):
    """Run backtest for a specific round."""
    print(f"Running backtest for round {round_num}...")
    print(f"Loading data from data/raw/round{round_num}/...")

    # TODO: Load historical data
    # TODO: Simulate order book and matching
    # TODO: Run trader.run() on each timestamp
    # TODO: Calculate PnL metrics (Sharpe, max drawdown, etc.)

    print("Backtest complete.")
    print(f"PnL: [TODO]")
    print(f"Sharpe Ratio: [TODO]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=1, help="Round number to backtest")
    args = parser.parse_args()

    run_backtest(args.round, None)
