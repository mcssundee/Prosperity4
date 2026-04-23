#!/usr/bin/env python3
"""Parameter sweep for round 2 strategy optimization."""

import subprocess
import json
import os
import re
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
TRADER_FILE = PROJECT_ROOT / "rounds/round2/algo/trader.py"
BASELINE_PNL = 298198

def run_backtest(params):
    """Run backtest with given parameters, return cumulative PnL."""
    trader_code = generate_trader(params)
    TRADER_FILE.write_text(trader_code)

    try:
        result = subprocess.run(
            ["python3", "backtesting/backtester.py", "--round", "2", "--merge-pnl"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120
        )

        pnl = None
        for line in result.stdout.split('\n'):
            if 'Total profit:' in line:
                match = re.search(r'Total profit: ([\d,]+)', line)
                if match:
                    pnl_str = match.group(1).replace(',', '')
                    pnl = int(pnl_str)
        return pnl
    except Exception as e:
        print(f"Backtest failed: {e}")
        return None

def generate_trader(params):
    """Generate trader.py code with given parameters."""
    return f'''from utils.datamodel import TradingState, Order
from typing import List
import json
from collections import defaultdict


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState) -> tuple[dict[str, list[Order]], int, str]:
        result = defaultdict(list)
        conversions = 0
        shared = {{}}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass
        result['ASH_COATED_OSMIUM'] = self.ash(state, shared)[0]
        ash_data = self.ash(state, shared)[1]
        result['INTARIAN_PEPPER_ROOT'] = self.root(state, shared)[0]
        root_data = self.root(state, shared)[1]
        traderData = json.dumps({{**ash_data, **root_data}})
        return dict(result), conversions, traderData

    def root(self, state: TradingState, shared: dict):
        product = 'INTARIAN_PEPPER_ROOT'
        result = []
        pos = state.position.get(product, 0)
        pos_lim = 80
        first_ask = shared.get("first_ask")
        peak_price = shared.get("peak_price")
        exited = shared.get("exited", False)

        root_data = {{"first_ask": first_ask, "peak_price": peak_price, "exited": exited}}

        if product not in state.order_depths:
            return result, root_data

        order_depth = state.order_depths[product]
        best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
        best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
            if peak_price is None:
                peak_price = mid_price
            else:
                peak_price = max(peak_price, mid_price)
            if not exited and mid_price < peak_price - {params['exit_threshold']}:
                exited = True
            elif exited and mid_price > peak_price - {params['reentry_threshold']}:
                exited = False
            root_data = {{"first_ask": first_ask, "peak_price": peak_price, "exited": exited}}

        if exited:
            if best_bid is not None and pos > 0:
                sell_qty = min(order_depth.buy_orders[best_bid], pos)
                if sell_qty > 0:
                    result.append(Order(product, best_bid, -sell_qty))
            return result, root_data

        if best_ask is None:
            return result, root_data

        if first_ask is None:
            first_ask = best_ask
            root_data["first_ask"] = first_ask

        if pos < {params['sweep_target']} and (best_ask <= first_ask + {params['sweep_ask_delta']} or state.timestamp >= {params['sweep_timestamp']}):
            qty = min({params['sweep_target']} - pos, abs(order_depth.sell_orders[best_ask]))
            if qty > 0:
                result.append(Order(product, best_ask, qty))
        elif pos < pos_lim:
            if best_bid is not None:
                result.append(Order(product, best_bid + 1, pos_lim - pos))

        return result, root_data

    def ash(self, state: TradingState, shared: dict):
        result = []
        pos_lim = 80
        quote_lim = {params['quote_lim']}
        sma_window = {params['sma_window']}
        bid_hist = shared.get("bid_hist", [])
        ask_hist = shared.get("ask_hist", [])
        if 'ASH_COATED_OSMIUM' not in state.order_depths:
            return result, {{"bid_hist": bid_hist, "ask_hist": ask_hist}}
        order_depth = state.order_depths['ASH_COATED_OSMIUM']
        bids = sorted(order_depth.buy_orders, reverse=True)
        asks = sorted(order_depth.sell_orders)
        curr_best_bid = bids[0] if len(bids) >= 1 else None
        curr_best_ask = asks[0] if len(asks) >= 1 else None
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)
        if best_bid is not None:
            bid_hist.append(best_bid)
        if best_ask is not None:
            ask_hist.append(best_ask)
        if len(bid_hist) > sma_window:
            bid_hist.pop(0)
        if len(ask_hist) > sma_window:
            ask_hist.pop(0)
        if len(bid_hist) < sma_window or len(ask_hist) < sma_window:
            return result, {{"bid_hist": bid_hist, "ask_hist": ask_hist}}
        bid_sma = sum(bid_hist) / sma_window
        ask_sma = sum(ask_hist) / sma_window
        fair_value = (bid_sma + ask_sma) / 2.0
        pos = state.position.get('ASH_COATED_OSMIUM', 0)
        buy_qty = min(quote_lim, pos_lim - pos)
        sell_qty = min(quote_lim, pos_lim + pos)
        best_bid = curr_best_bid if curr_best_bid is not None else (bid_hist[-1] if bid_hist else None)
        best_ask = curr_best_ask if curr_best_ask is not None else (ask_hist[-1] if ask_hist else None)
        if fair_value is not None:
            buy_threshold = fair_value + (1 if pos < {params['pos_threshold_buy']} else 0)
            sell_threshold = fair_value - (1 if pos > {params['pos_threshold_sell']} else 0)
            for ask_px in asks:
                if ask_px <= buy_threshold and buy_qty != 0 and pos <= {params['max_active_pos']}:
                    result.append(Order('ASH_COATED_OSMIUM', ask_px, buy_qty))
                    buy_qty = 0
                    break
            for bid_px in bids:
                if bid_px >= sell_threshold and sell_qty != 0 and pos >= -{params['max_active_pos']}:
                    result.append(Order('ASH_COATED_OSMIUM', bid_px, -sell_qty))
                    sell_qty = 0
                    break
        passive_bid = next((p for p in bids if p + 1 <= fair_value), None) if fair_value is not None else best_bid
        if passive_bid is None and best_bid is not None and (fair_value is None or best_bid + 1 <= fair_value):
            passive_bid = best_bid
        passive_ask = next((p for p in asks if p - 1 >= fair_value), None) if fair_value is not None else best_ask
        if passive_ask is None and best_ask is not None and (fair_value is None or best_ask - 1 >= fair_value):
            passive_ask = best_ask
        if passive_bid is not None and buy_qty != 0:
            result.append(Order('ASH_COATED_OSMIUM', passive_bid + 1, buy_qty))
        if passive_ask is not None and sell_qty != 0:
            result.append(Order('ASH_COATED_OSMIUM', passive_ask - 1, -sell_qty))
        return result, {{"bid_hist": bid_hist, "ask_hist": ask_hist}}
'''

def phase1_test():
    """Phase 1: Test SMA window and quote limit."""
    print("=" * 60)
    print("PHASE 1: SMA Window & Quote Limit Optimization")
    print("=" * 60)

    results = defaultdict(list)
    configs = []

    for sma in [3, 5, 7, 10]:
        for quote in [5, 10, 15, 20]:
            configs.append({
                'sma_window': sma,
                'quote_lim': quote,
                'pos_threshold_buy': -15,
                'pos_threshold_sell': 15,
                'max_active_pos': 40,
                'exit_threshold': 50,
                'reentry_threshold': 25,
                'sweep_target': 76,
                'sweep_ask_delta': 2,
                'sweep_timestamp': 2000
            })

    for i, config in enumerate(configs, 1):
        pnl = run_backtest(config)
        if pnl:
            gain = ((pnl - BASELINE_PNL) / BASELINE_PNL) * 100
            print(f"[{i}/{len(configs)}] SMA={config['sma_window']}, Quote={config['quote_lim']}: PnL={pnl:,} ({gain:+.2f}%)")
            results[(config['sma_window'], config['quote_lim'])] = pnl
        else:
            print(f"[{i}/{len(configs)}] SMA={config['sma_window']}, Quote={config['quote_lim']}: FAILED")

    best = max(results.items(), key=lambda x: x[1]) if results else None
    if best:
        print(f"\n✓ Best Phase 1: SMA={best[0][0]}, Quote={best[0][1]} → {best[1]:,}")
        return {'sma_window': best[0][0], 'quote_lim': best[0][1]}
    return {'sma_window': 5, 'quote_lim': 10}

def phase2b_test_sweep_params():
    """Phase 2b: Test sweep target and ask delta (ROOT accumulation)."""
    print("\n" + "=" * 60)
    print("PHASE 2B: ROOT Sweep Accumulation Optimization")
    print("=" * 60)

    results = defaultdict(list)
    configs = []

    for sweep_tgt in [50, 60, 70, 76, 80]:
        for ask_delta in [1, 2, 3, 5]:
            configs.append({
                'sma_window': 5,
                'quote_lim': 10,
                'pos_threshold_buy': -15,
                'pos_threshold_sell': 15,
                'max_active_pos': 40,
                'exit_threshold': 50,
                'reentry_threshold': 25,
                'sweep_target': sweep_tgt,
                'sweep_ask_delta': ask_delta,
                'sweep_timestamp': 2000
            })

    for i, config in enumerate(configs, 1):
        pnl = run_backtest(config)
        if pnl:
            gain = ((pnl - BASELINE_PNL) / BASELINE_PNL) * 100
            print(f"[{i}/{len(configs)}] Sweep={config['sweep_target']}, Delta={config['sweep_ask_delta']}: PnL={pnl:,} ({gain:+.2f}%)")
            results[(config['sweep_target'], config['sweep_ask_delta'])] = pnl
        else:
            print(f"[{i}/{len(configs)}] Sweep={config['sweep_target']}, Delta={config['sweep_ask_delta']}: FAILED")

    best = max(results.items(), key=lambda x: x[1]) if results else None
    if best:
        print(f"\n✓ Best Sweep: Target={best[0][0]}, Delta={best[0][1]} → {best[1]:,}")
        return {'sweep_target': best[0][0], 'sweep_ask_delta': best[0][1]}
    return {'sweep_target': 76, 'sweep_ask_delta': 2}

def phase2_test():
    """Phase 2: Test ROOT strategy parameters (exit/reentry thresholds)."""
    print("\n" + "=" * 60)
    print("PHASE 2: ROOT Exit/Re-entry & Sweep Optimization")
    print("=" * 60)

    results = defaultdict(list)
    configs = []

    for exit_th in [30, 50, 75, 100]:
        for reentry_th in [10, 25, 40, 60]:
            configs.append({
                'sma_window': 5,
                'quote_lim': 10,
                'pos_threshold_buy': -15,
                'pos_threshold_sell': 15,
                'max_active_pos': 40,
                'exit_threshold': exit_th,
                'reentry_threshold': reentry_th,
                'sweep_target': 76,
                'sweep_ask_delta': 2,
                'sweep_timestamp': 2000
            })

    for i, config in enumerate(configs, 1):
        pnl = run_backtest(config)
        if pnl:
            gain = ((pnl - BASELINE_PNL) / BASELINE_PNL) * 100
            print(f"[{i}/{len(configs)}] Exit={config['exit_threshold']}, Reentry={config['reentry_threshold']}: PnL={pnl:,} ({gain:+.2f}%)")
            results[(config['exit_threshold'], config['reentry_threshold'])] = pnl
        else:
            print(f"[{i}/{len(configs)}] Exit={config['exit_threshold']}, Reentry={config['reentry_threshold']}: FAILED")

    best = max(results.items(), key=lambda x: x[1]) if results else None
    if best:
        print(f"\n✓ Best Phase 2: Exit={best[0][0]}, Reentry={best[0][1]} → {best[1]:,}")
        return {'exit_threshold': best[0][0], 'reentry_threshold': best[0][1]}
    return {'exit_threshold': 50, 'reentry_threshold': 25}

def phase3_test_aggressive():
    """Phase 3: Test more aggressive settings."""
    print("\n" + "=" * 60)
    print("PHASE 3: Aggressive Configuration Testing")
    print("=" * 60)

    configs = [
        {'name': 'More aggressive ASH (quote_lim=30)', 'sma_window': 5, 'quote_lim': 30, 'pos_threshold_buy': -20, 'pos_threshold_sell': 20, 'max_active_pos': 50, 'exit_threshold': 50, 'reentry_threshold': 25, 'sweep_target': 76, 'sweep_ask_delta': 2, 'sweep_timestamp': 2000},
        {'name': 'Faster sweep (target=80)', 'sma_window': 5, 'quote_lim': 10, 'pos_threshold_buy': -15, 'pos_threshold_sell': 15, 'max_active_pos': 40, 'exit_threshold': 50, 'reentry_threshold': 25, 'sweep_target': 80, 'sweep_ask_delta': 2, 'sweep_timestamp': 2000},
        {'name': 'Earlier sweep (timestamp=1500)', 'sma_window': 5, 'quote_lim': 10, 'pos_threshold_buy': -15, 'pos_threshold_sell': 15, 'max_active_pos': 40, 'exit_threshold': 50, 'reentry_threshold': 25, 'sweep_target': 76, 'sweep_ask_delta': 2, 'sweep_timestamp': 1500},
        {'name': 'Tighter trailing stop (exit=30)', 'sma_window': 5, 'quote_lim': 10, 'pos_threshold_buy': -15, 'pos_threshold_sell': 15, 'max_active_pos': 40, 'exit_threshold': 30, 'reentry_threshold': 15, 'sweep_target': 76, 'sweep_ask_delta': 2, 'sweep_timestamp': 2000},
        {'name': 'Larger max_active_pos=60', 'sma_window': 5, 'quote_lim': 10, 'pos_threshold_buy': -15, 'pos_threshold_sell': 15, 'max_active_pos': 60, 'exit_threshold': 50, 'reentry_threshold': 25, 'sweep_target': 76, 'sweep_ask_delta': 2, 'sweep_timestamp': 2000},
    ]

    for i, config in enumerate(configs, 1):
        name = config.pop('name')
        pnl = run_backtest(config)
        if pnl:
            gain = ((pnl - BASELINE_PNL) / BASELINE_PNL) * 100
            print(f"[{i}/{len(configs)}] {name}: PnL={pnl:,} ({gain:+.2f}%)")
        else:
            print(f"[{i}/{len(configs)}] {name}: FAILED")

if __name__ == "__main__":
    print(f"Baseline PnL: {BASELINE_PNL:,}\n")
    phase1_best = phase1_test()
    phase2_best = phase2_test()
    phase2b_best = phase2b_test_sweep_params()
    phase3_best = phase3_test_aggressive()
    print("\nOptimization complete.")
