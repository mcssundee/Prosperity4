#!/usr/bin/env bash
# Run prosperity4bt from project root.
# Usage:
#   ./backtesting/run.sh trader.py 4          # all days in round 4
#   ./backtesting/run.sh trader.py 4-1        # round 4, day 1 only
#   ./backtesting/run.sh trader.py 4-1 4-2    # round 4, days 1 and 2
#   ./backtesting/run.sh trader.py 4 --no-vis # skip opening visualizer
#
# Extra flags are passed through to prosperity4bt (e.g. --no-merge-pnl, --print).

cd "$(dirname "$0")/.." || exit 1

REPO="$(pwd)/backtesting/prosperity4bt_repo"
export PYTHONPATH="$REPO:$PYTHONPATH"

python3 -m prosperity4bt "$@"
