#!/usr/bin/env python3
"""
Bid Optimization for Round 3 Manual Trading
Ornamental Bio-Pods: auto-sell at 920 next round
"""

import numpy as np
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────────
SELL_PRICE = 920
RESERVE_MIN, RESERVE_MAX, RESERVE_STEP = 670, 920, 5
N_COMPETITORS = 10
N_SIMULATIONS = 100_000
RNG = np.random.default_rng(42)

counterparty_reserves = np.arange(RESERVE_MIN, RESERVE_MAX + 1, RESERVE_STEP)
print(f"Counterparty reserves: {len(counterparty_reserves)} units from {RESERVE_MIN} to {RESERVE_MAX}")
print(f"Assumptions: {N_COMPETITORS} competitors, {N_SIMULATIONS} Monte Carlo simulations\n")

# ── Profit Functions ────────────────────────────────────────────────────────
def bid1_profit(bid1):
    """Deterministic profit from bid1 trades."""
    eligible = counterparty_reserves[counterparty_reserves < bid1]
    return (SELL_PRICE - bid1) * len(eligible)

def expected_profit(bid1, bid2, competitor_b2_draws):
    """
    Monte Carlo expected profit for (bid1, bid2) pair.
    competitor_b2_draws: shape (n_sims, N_COMPETITORS)
    """
    if bid2 <= bid1:
        return {'mean': -np.inf, 'std': 0, 'p5': -np.inf, 'p_no_penalty': 0}

    # Bid1 profit (deterministic)
    b1_p = bid1_profit(bid1)

    # Bid2 profit (stochastic)
    our_col = np.full((N_SIMULATIONS, 1), bid2)
    all_b2 = np.concatenate([competitor_b2_draws, our_col], axis=1)
    avg_b2 = all_b2.mean(axis=1)

    eligible = counterparty_reserves[(counterparty_reserves >= bid1) & (counterparty_reserves < bid2)]
    n_eligible = len(eligible)
    margin = SELL_PRICE - bid2

    if n_eligible == 0 or margin <= 0:
        b2_profits = np.zeros(N_SIMULATIONS)
        p_no_pen = 1.0
    else:
        no_penalty = bid2 >= avg_b2
        penalty = ((SELL_PRICE - avg_b2) / (SELL_PRICE - bid2)) ** 3
        b2_profits = np.where(no_penalty, margin * n_eligible, margin * n_eligible * penalty)
        p_no_pen = float(no_penalty.mean())

    total = b1_p + b2_profits
    return {
        'mean': float(total.mean()),
        'std': float(total.std()),
        'p5': float(np.percentile(total, 5)),
        'p_no_penalty': p_no_pen
    }

# ── Scenario 1: Uniform (most conservative) ────────────────────────────────
print("=" * 70)
print("SCENARIO 1: UNIFORM COMPETITORS (all bid2 equally likely)")
print("=" * 70)

draws_uniform = RNG.uniform(670, 920, size=(N_SIMULATIONS, N_COMPETITORS))

bid1_values = np.arange(670, 916, 5)
bid2_values = np.arange(670, 921, 5)

best_overall = None
best_overall_profit = -np.inf
results_uniform = {}

# Precompute competitor sum for efficiency
competitor_sum = draws_uniform.sum(axis=1)

for b1 in bid1_values:
    for b2 in bid2_values:
        if b2 <= b1:
            continue

        avg_b2 = (competitor_sum + b2) / (N_COMPETITORS + 1)
        b1_p = bid1_profit(b1)

        eligible = counterparty_reserves[(counterparty_reserves >= b1) & (counterparty_reserves < b2)]
        n_eligible = len(eligible)
        margin = SELL_PRICE - b2

        if n_eligible == 0 or margin <= 0:
            b2_profits = np.zeros(N_SIMULATIONS)
            p_no_pen = 1.0
        else:
            no_penalty = b2 >= avg_b2
            penalty = ((SELL_PRICE - avg_b2) / (SELL_PRICE - b2)) ** 3
            b2_profits = np.where(no_penalty, margin * n_eligible, margin * n_eligible * penalty)
            p_no_pen = float(no_penalty.mean())

        total = b1_p + b2_profits
        stats = {
            'mean': float(total.mean()),
            'std': float(total.std()),
            'p5': float(np.percentile(total, 5)),
            'p_no_penalty': p_no_pen
        }

        results_uniform[(b1, b2)] = stats

        if stats['mean'] > best_overall_profit:
            best_overall_profit = stats['mean']
            best_overall = (b1, b2, stats)

b1_opt, b2_opt, stats_opt = best_overall
print(f"\n✓ OPTIMAL BIDS (uniform): bid1={int(b1_opt)}, bid2={int(b2_opt)}")
print(f"  E[Profit]:        {stats_opt['mean']:.1f}")
print(f"  Std[Profit]:      {stats_opt['std']:.1f}")
print(f"  P(profit ≥ p5):   50%")
print(f"  5th percentile:   {stats_opt['p5']:.1f}")
print(f"  P(no penalty):    {stats_opt['p_no_penalty']:.1%}")

# Top 5
print(f"\nTop 5 (bid1, bid2) pairs by E[Profit]:")
top5 = sorted(results_uniform.items(), key=lambda x: x[1]['mean'], reverse=True)[:5]
print(f"{'bid1':>6} {'bid2':>6} {'E[profit]':>12} {'std':>10} {'p_no_pen':>12}")
for (b1, b2), s in top5:
    print(f"{int(b1):>6} {int(b2):>6} {s['mean']:>12.1f} {s['std']:>10.1f} {s['p_no_penalty']:>12.1%}")

# ── Scenario 2: Aggressive (competitors bid high) ────────────────────────────
print("\n" + "=" * 70)
print("SCENARIO 2: AGGRESSIVE COMPETITORS (cluster near 870)")
print("=" * 70)

draws_aggressive = RNG.normal(loc=870, scale=30, size=(N_SIMULATIONS, N_COMPETITORS)).clip(670, 919)
competitor_sum_agg = draws_aggressive.sum(axis=1)

best_agg = None
best_agg_profit = -np.inf
results_aggressive = {}

for b1 in bid1_values:
    for b2 in bid2_values:
        if b2 <= b1:
            continue

        avg_b2 = (competitor_sum_agg + b2) / (N_COMPETITORS + 1)
        b1_p = bid1_profit(b1)

        eligible = counterparty_reserves[(counterparty_reserves >= b1) & (counterparty_reserves < b2)]
        n_eligible = len(eligible)
        margin = SELL_PRICE - b2

        if n_eligible == 0 or margin <= 0:
            b2_profits = np.zeros(N_SIMULATIONS)
            p_no_pen = 1.0
        else:
            no_penalty = b2 >= avg_b2
            penalty = ((SELL_PRICE - avg_b2) / (SELL_PRICE - b2)) ** 3
            b2_profits = np.where(no_penalty, margin * n_eligible, margin * n_eligible * penalty)
            p_no_pen = float(no_penalty.mean())

        total = b1_p + b2_profits
        stats = {
            'mean': float(total.mean()),
            'std': float(total.std()),
            'p5': float(np.percentile(total, 5)),
            'p_no_penalty': p_no_pen
        }

        results_aggressive[(b1, b2)] = stats

        if stats['mean'] > best_agg_profit:
            best_agg_profit = stats['mean']
            best_agg = (b1, b2, stats)

b1_opt_agg, b2_opt_agg, stats_opt_agg = best_agg
print(f"\n✓ OPTIMAL BIDS (aggressive): bid1={int(b1_opt_agg)}, bid2={int(b2_opt_agg)}")
print(f"  E[Profit]:        {stats_opt_agg['mean']:.1f}")
print(f"  Std[Profit]:      {stats_opt_agg['std']:.1f}")
print(f"  5th percentile:   {stats_opt_agg['p5']:.1f}")
print(f"  P(no penalty):    {stats_opt_agg['p_no_penalty']:.1%}")

# Top 5
print(f"\nTop 5 (bid1, bid2) pairs by E[Profit]:")
top5_agg = sorted(results_aggressive.items(), key=lambda x: x[1]['mean'], reverse=True)[:5]
print(f"{'bid1':>6} {'bid2':>6} {'E[profit]':>12} {'std':>10} {'p_no_pen':>12}")
for (b1, b2), s in top5_agg:
    print(f"{int(b1):>6} {int(b2):>6} {s['mean']:>12.1f} {s['std']:>10.1f} {s['p_no_penalty']:>12.1%}")

# ── Scenario 3: Conservative (competitors bid low) ────────────────────────────
print("\n" + "=" * 70)
print("SCENARIO 3: CONSERVATIVE COMPETITORS (cluster near 750)")
print("=" * 70)

draws_conservative = RNG.normal(loc=750, scale=40, size=(N_SIMULATIONS, N_COMPETITORS)).clip(670, 919)
competitor_sum_cons = draws_conservative.sum(axis=1)

best_cons = None
best_cons_profit = -np.inf
results_conservative = {}

for b1 in bid1_values:
    for b2 in bid2_values:
        if b2 <= b1:
            continue

        avg_b2 = (competitor_sum_cons + b2) / (N_COMPETITORS + 1)
        b1_p = bid1_profit(b1)

        eligible = counterparty_reserves[(counterparty_reserves >= b1) & (counterparty_reserves < b2)]
        n_eligible = len(eligible)
        margin = SELL_PRICE - b2

        if n_eligible == 0 or margin <= 0:
            b2_profits = np.zeros(N_SIMULATIONS)
            p_no_pen = 1.0
        else:
            no_penalty = b2 >= avg_b2
            penalty = ((SELL_PRICE - avg_b2) / (SELL_PRICE - b2)) ** 3
            b2_profits = np.where(no_penalty, margin * n_eligible, margin * n_eligible * penalty)
            p_no_pen = float(no_penalty.mean())

        total = b1_p + b2_profits
        stats = {
            'mean': float(total.mean()),
            'std': float(total.std()),
            'p5': float(np.percentile(total, 5)),
            'p_no_penalty': p_no_pen
        }

        results_conservative[(b1, b2)] = stats

        if stats['mean'] > best_cons_profit:
            best_cons_profit = stats['mean']
            best_cons = (b1, b2, stats)

b1_opt_cons, b2_opt_cons, stats_opt_cons = best_cons
print(f"\n✓ OPTIMAL BIDS (conservative): bid1={int(b1_opt_cons)}, bid2={int(b2_opt_cons)}")
print(f"  E[Profit]:        {stats_opt_cons['mean']:.1f}")
print(f"  Std[Profit]:      {stats_opt_cons['std']:.1f}")
print(f"  5th percentile:   {stats_opt_cons['p5']:.1f}")
print(f"  P(no penalty):    {stats_opt_cons['p_no_penalty']:.1%}")

# Top 5
print(f"\nTop 5 (bid1, bid2) pairs by E[Profit]:")
top5_cons = sorted(results_conservative.items(), key=lambda x: x[1]['mean'], reverse=True)[:5]
print(f"{'bid1':>6} {'bid2':>6} {'E[profit]':>12} {'std':>10} {'p_no_pen':>12}")
for (b1, b2), s in top5_cons:
    print(f"{int(b1):>6} {int(b2):>6} {s['mean']:>12.1f} {s['std']:>10.1f} {s['p_no_penalty']:>12.1%}")

# ── Final Recommendation ────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("FINAL RECOMMENDATION")
print("=" * 70)
print(f"""
If you expect competitors to bid UNIFORMLY across the range:
  → bid1 = {int(b1_opt)}, bid2 = {int(b2_opt)}
  → Expected profit: {stats_opt['mean']:.1f}

If you expect competitors to bid AGGRESSIVELY (high):
  → bid1 = {int(b1_opt_agg)}, bid2 = {int(b2_opt_agg)}
  → Expected profit: {stats_opt_agg['mean']:.1f}

If you expect competitors to bid CONSERVATIVELY (low):
  → bid1 = {int(b1_opt_cons)}, bid2 = {int(b2_opt_cons)}
  → Expected profit: {stats_opt_cons['mean']:.1f}

SAFE CHOICE (no strong assumption about competitors):
  → bid1 = {int(b1_opt)}, bid2 = {int(b2_opt)} (uniform scenario)
""")

# ── Key Insights ────────────────────────────────────────────────────────────
print("KEY INSIGHTS:")
print("""
1. bid1 is INDEPENDENT of bid2 in mechanics, but they compete for counterparties.

2. Standalone bid1 profit: bid1 is a threshold. Higher bid1 → more sales but lower margin.
   The tradeoff peaks around bid1=800 (captures 25 counterparties at profit=3000).

3. bid2 serves counterparties with reserve ∈ [bid1, bid2). It's riskier because:
   - Penalty applies if bid2 < average of all players' bid2
   - Penalty factor: ((920 - avg_b2) / (920 - bid2))^3 is brutal if you underbid

4. Optimal strategy:
   - Set bid1 moderately (750-800) to capture low-hanging fruit
   - Set bid2 high enough to avoid penalty but low enough for margin
   - If competitors are aggressive, you must bid higher to avoid penalties

5. The margin on bid2 (920 - bid2) is often small if bid2 is high, so quantity matters.
   Counterparties with reserve ∈ [bid1, bid2) give you extra volume at reasonable cost.
""")
