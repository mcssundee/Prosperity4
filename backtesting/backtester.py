#!/usr/bin/env python3
"""Backtesting wrapper for prosperity4btest."""

import subprocess
import argparse
import sys


def run_backtest(round_spec, vis=False, merge_pnl=False, print_output=False):
    """
    Run backtest using prosperity4btest CLI.

    Args:
        round_spec: Round number or round-day spec (e.g., "1", "1-0", "1--1 1-0")
        vis: Open visualizer in browser after backtest
        merge_pnl: Carry PnL forward across days
        print_output: Print trader's stdout during backtest
    """
    cmd = ["prosperity4btest", "rounds/round1/algo/trader.py", str(round_spec)]

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
    parser.add_argument("round", type=str, nargs="?", default="1", help="Round spec: '1' (all days) or '1-0' (specific day)")
    parser.add_argument("--vis", action="store_true", help="Open visualizer in browser")
    parser.add_argument("--merge-pnl", action="store_true", help="Carry PnL forward across days")
    parser.add_argument("--print", action="store_true", help="Print trader's stdout during backtest")
    args = parser.parse_args()

    exit_code = run_backtest(args.round, vis=args.vis, merge_pnl=args.merge_pnl, print_output=args.print)
    sys.exit(exit_code)
