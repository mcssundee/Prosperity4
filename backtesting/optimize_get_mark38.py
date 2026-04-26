"""
Parameter sweep optimizer for get_mark38_test.py using prosperity4bt internals.
Run from project root:
    PYTHONPATH=backtesting/prosperity4bt_repo:backtesting/prosperity4bt_repo/prosperity4bt \
        python3 backtesting/optimize_get_mark38.py --iter 1
"""

import sys, os, argparse, itertools, json, types
from pathlib import Path

# --- make prosperity4bt importable ------------------------------------------
REPO = Path(__file__).parent / "prosperity4bt_repo"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prosperity4bt"))

from prosperity4bt.tools.data_reader import PackageResourcesReader
from prosperity4bt.test_runner import TestRunner
from prosperity4bt.models.test_options import TradeMatchingMode

# ---------------------------------------------------------------------------
# Parameterised Trader
# ---------------------------------------------------------------------------

def make_trader(alpha, take_thresh, spread, skew_div, quote_size):
    """Return a fresh Trader instance with given parameters."""
    from prosperity4bt.datamodel import Order

    class Trader:
        def __init__(self):
            self._alpha = alpha
            self._take_thresh = take_thresh
            self._spread = spread
            self._skew_div = skew_div
            self._quote_size = quote_size

        def run(self, state):
            result = {}
            conversions = 0
            shared = {}
            if state.traderData:
                try:
                    shared = json.loads(state.traderData)
                except json.JSONDecodeError:
                    pass

            result['HYDROGEL_PACK'], hp_data = self._hydrogel(state, shared)
            return result, conversions, json.dumps(hp_data)

        def _hydrogel(self, state, shared):
            product = 'HYDROGEL_PACK'
            pos_lim = 200
            ema = shared.get('hp_ema')

            od = state.order_depths.get(product)
            if not od or not od.buy_orders or not od.sell_orders:
                return [], {'hp_ema': ema}

            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            mid = (best_bid + best_ask) / 2.0

            ema = mid if ema is None else self._alpha * mid + (1 - self._alpha) * ema
            fair = ema

            pos = state.position.get(product, 0)
            skew = -round(pos / self._skew_div)
            bid_px = round(fair - self._spread + skew)
            ask_px = round(fair + self._spread + skew)
            if bid_px >= ask_px:
                bid_px = ask_px - 1

            buy_cap = pos_lim - pos
            sell_cap = pos_lim + pos
            orders = []

            for ask in sorted(od.sell_orders):
                if ask <= fair - self._take_thresh and buy_cap > 0:
                    qty = min(buy_cap, abs(od.sell_orders[ask]))
                    orders.append(Order(product, ask, qty))
                    buy_cap -= qty
            for bid in sorted(od.buy_orders, reverse=True):
                if bid >= fair + self._take_thresh and sell_cap > 0:
                    qty = min(sell_cap, od.buy_orders[bid])
                    orders.append(Order(product, bid, -qty))
                    sell_cap -= qty

            if buy_cap > 0:
                orders.append(Order(product, bid_px, min(self._quote_size, buy_cap)))
            if sell_cap > 0:
                orders.append(Order(product, ask_px, -min(self._quote_size, sell_cap)))

            return orders, {'hp_ema': ema}

    return Trader()


# ---------------------------------------------------------------------------
# Evaluate one parameter set over all 3 days
# ---------------------------------------------------------------------------

def evaluate(params, reader, days=(1, 2, 3)):
    trader = make_trader(**params)
    total = 0
    for day in days:
        runner = TestRunner(trader, reader, round=4, day=day,
                            show_progress_bar=False, print_output=False,
                            trade_matching_mode=TradeMatchingMode.server_like)
        result = runner.run()
        # carry traderData across days
        last_trader_data = ""
        if result.sandbox_logs:
            last_trader_data = result.sandbox_logs[-1].lambda_log
        profit = sum(a.profit_loss for a in result.final_activities())
        total += profit
    return total


# ---------------------------------------------------------------------------
# Parameter grids for each iteration
# ---------------------------------------------------------------------------

GRIDS = {
    1: {  # coarse sweep: find the right spread & alpha
        "alpha":       [0.01, 0.05, 0.1, 0.2, 0.4],
        "take_thresh": [5, 10, 15, 20],
        "spread":      [2, 3, 4, 5, 6],
        "skew_div":    [40],
        "quote_size":  [6],
    },
    2: {  # mid sweep: refine skew_div and quote_size around best from iter 1
        # filled in dynamically from iter-1 best
        "alpha":       None,
        "take_thresh": None,
        "spread":      None,
        "skew_div":    [10, 20, 30, 40, 60, 80],
        "quote_size":  [3, 6, 10, 20, 50],
    },
    3: {  # fine sweep: tighten alpha and spread around best from iter 2
        "alpha":       None,
        "take_thresh": None,
        "spread":      None,
        "skew_div":    None,
        "quote_size":  None,
        # ranges populated dynamically
    },
}


def expand_grid(grid):
    keys = list(grid.keys())
    values = list(grid.values())
    for combo in itertools.product(*values):
        yield dict(zip(keys, combo))


def run_sweep(grid, reader):
    results = []
    combos = list(expand_grid(grid))
    print(f"  Testing {len(combos)} parameter combinations…")
    for i, params in enumerate(combos, 1):
        pnl = evaluate(params, reader)
        results.append((pnl, params))
        if i % 20 == 0:
            best_so_far = max(results, key=lambda x: x[0])
            print(f"  [{i}/{len(combos)}] best so far: {best_so_far[0]:,.0f} — {best_so_far[1]}")
    results.sort(key=lambda x: -x[0])
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iter", type=int, choices=[1, 2, 3], default=1)
    parser.add_argument("--best-params", type=str, default=None,
                        help="JSON string of best params from previous iteration (for iter 2/3)")
    args = parser.parse_args()

    reader = PackageResourcesReader()

    # ---- baseline ----------------------------------------------------------
    baseline_params = dict(alpha=0.05, take_thresh=10, spread=4, skew_div=40, quote_size=6)
    print("=== Baseline ===")
    baseline_pnl = evaluate(baseline_params, reader)
    print(f"  Total PnL: {baseline_pnl:,.0f}\n")

    # ---- load previous best if provided ------------------------------------
    prev_best = json.loads(args.best_params) if args.best_params else baseline_params

    # ---- build grid --------------------------------------------------------
    if args.iter == 1:
        grid = GRIDS[1]

    elif args.iter == 2:
        b = prev_best
        grid = {
            "alpha":       [max(0.001, b["alpha"] / 2), b["alpha"], min(0.9, b["alpha"] * 2)],
            "take_thresh": [max(1, b["take_thresh"] - 5), b["take_thresh"], b["take_thresh"] + 5],
            "spread":      [max(1, b["spread"] - 1), b["spread"], b["spread"] + 1],
            "skew_div":    [10, 20, 30, 40, 60, 80],
            "quote_size":  [3, 6, 10, 20, 50],
        }

    elif args.iter == 3:
        b = prev_best
        def linspace(lo, hi, n):
            if lo == hi:
                return [lo]
            step = (hi - lo) / (n - 1)
            return [round(lo + step * i, 4) for i in range(n)]

        grid = {
            "alpha":       linspace(max(0.001, b["alpha"] * 0.5), min(0.9, b["alpha"] * 1.5), 5),
            "take_thresh": [max(1, b["take_thresh"] - 3), b["take_thresh"], b["take_thresh"] + 3],
            "spread":      [max(1, b["spread"] - 1), b["spread"], b["spread"] + 1],
            "skew_div":    [max(5, b["skew_div"] - 10), b["skew_div"], b["skew_div"] + 10],
            "quote_size":  [max(1, b["quote_size"] - 3), b["quote_size"], b["quote_size"] + 3],
        }

    print(f"=== Iteration {args.iter} sweep ===")
    results = run_sweep(grid, reader)

    print(f"\nTop 5 results (iteration {args.iter}):")
    for pnl, params in results[:5]:
        print(f"  PnL: {pnl:>10,.0f}  params: {params}")

    best_pnl, best_params = results[0]
    print(f"\nBest: {best_pnl:,.0f}  vs baseline {baseline_pnl:,.0f}"
          f"  (delta {best_pnl - baseline_pnl:+,.0f})")
    print(f"\nTo run next iteration, pass:")
    print(f"  --best-params '{json.dumps(best_params)}'")


if __name__ == "__main__":
    main()
