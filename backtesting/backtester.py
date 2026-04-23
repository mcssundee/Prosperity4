#!/usr/bin/env python3
"""Backtesting wrapper for prosperity4btest."""

import subprocess
import argparse
import sys
from pathlib import Path


def run_backtest(round_num, round_spec=None, vis=False, merge_pnl=False, print_output=False):
    """
    Run backtest using prosperity4btest CLI.

    Args:
        round_num: Round number (1-5)
        round_spec: Day spec (e.g., "-1", "0", "-1 0"). If None, runs all days.
        vis: Open visualizer in browser after backtest
        merge_pnl: Carry PnL forward across days
        print_output: Print trader's stdout during backtest
    """
    trader_file = Path(f"rounds/round{round_num}/algo/trader.py").absolute()
    if not trader_file.exists():
        print(f"Error: {trader_file} not found", file=sys.stderr)
        return 1

    if round_spec is None:
        spec = str(round_num)
    else:
        spec = f"{round_num}-{round_spec.lstrip('-')}"

    cmd = ["python3", "-m", "prosperity4bt", "cli", str(trader_file), spec]

    if vis:
        cmd.append("--vis")
    if merge_pnl:
        cmd.append("--merge-pnl")
    if print_output:
        cmd.append("--print")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest trading algorithm with prosperity4btest")
    parser.add_argument("--round", type=int, default=1, help="Round number (1-5)")
    parser.add_argument("--day", type=str, help="Specific day(s): '-1', '0', '-1 0', etc. If omitted, runs all days.")
    parser.add_argument("--vis", action="store_true", help="Open visualizer in browser")
    parser.add_argument("--merge-pnl", action="store_true", help="Carry PnL forward across days")
    parser.add_argument("--print", action="store_true", help="Print trader's stdout during backtest")
    args = parser.parse_args()

    exit_code = run_backtest(args.round, round_spec=args.day, vis=args.vis, merge_pnl=args.merge_pnl, print_output=args.print)
    sys.exit(exit_code)
