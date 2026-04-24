# Round 3 Trading Strategy Plan

## Context

Round 3 ("Gloves Off") introduces three new products on planet Solvenar with a reset leaderboard:
- **HYDROGEL_PACK** (pos limit 200): Mean-reverting around 10000 (spread ±8 bid/ask sides, like Rainforest Resin)
- **VELVETFRUIT_EXTRACT** (pos limit 200): Mean-reverting around 5250 (tight spread ~5-6 ticks)
- **10 VEV Vouchers** (pos limit 300 each): European call options on VEV, strikes 4000–6500, TTE = 5 days at round start

Top competitors (Frankfurt Hedgehogs, CMU Physics) made 100–150k SeaShells/round from IV scalping options. The strategy is: back out implied volatility from market prices, fit a vol smile across strikes, reprice each option from the smile, and trade deviations. Skip delta hedging (CMU finding: hedge costs 40k+ in spread costs, net negative vs. unhedged).

## Files to Modify

- `rounds/round3/algo/trader.py` — implement from scratch (current: 14-line skeleton)
- `trader.py` — copy of the above for submission

## Implementation Design

### Helper Math (no scipy — use `math.erf`)

```python
def _norm_cdf(x):
    return (1 + math.erf(x / math.sqrt(2))) / 2

def _bs_call(S, K, T, sigma):
    # S: spot, K: strike, T: years, sigma: annualized vol
    # Returns intrinsic if T <= 0
    if T <= 1e-9: return max(S - K, 0.0)
    d1 = (math.log(S/K) + 0.5*sigma**2*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    return S*_norm_cdf(d1) - K*_norm_cdf(d2)

def _implied_vol(S, K, T, price):
    # Bisection, 200 iter, tol=1e-6
    intrinsic = max(S - K, 0.0)
    if price <= intrinsic + 1e-9 or T <= 1e-9: return None
    lo, hi = 1e-6, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _bs_call(S, K, T, mid) > price: hi = mid
        else: lo = mid
        if hi - lo < 1e-6: break
    return (lo + hi) / 2

def _fit_quadratic(xs, ys):
    # Least-squares quadratic fit y = a*x^2 + b*x + c
    # Returns (a, b, c) or None if degenerate
    # Solves 3x3 normal equations manually
```

### TTE Tracking

- TTE (in years) = `(base_tte_days - day_count - timestamp/1e6) / 365`
- `base_tte_days = 5` for submission (round 3 live); for backtesting historical data (days 0,1,2 = TTE 8,7,6), detect via timestamp reset
- Day transition: if `state.timestamp < shared.get("prev_ts", 0)`, increment `day_count`
- Min TTE clamped to 0.001 to avoid division by zero

### Strategy 1: `hydrogel(state, shared)`

HYDROGEL_PACK is Rainforest Resin equivalent — observed stable at 10000.

- Fair value = 10000 (hardcoded)
- Active take: buy all asks ≤ 9999; sell all bids ≥ 10001 (while within pos limit)
- Passive make: place bid at 9999, ask at 10001 with `quote_lim = 15` remaining capacity
- Position limit 200, quote limit 15

### Strategy 2: `vev_spot(state, shared)`

VELVETFRUIT_EXTRACT is a clean mean-reverting asset.

- Rolling SMA-5 fair value (same pattern as ASH_COATED_OSMIUM in round 2)
- Active take: buy asks ≤ fair−1; sell bids ≥ fair+1
- Passive make: best resting quotes ±1 from fair
- Position limit 200, quote limit 10

### Strategy 3: `vev_options(state, shared)`

Core alpha source. 10 vouchers split into three tiers:

**Tier A — Deep ITM (VEV_4000, VEV_4500): delta ≈ 1, track underlying**
- Fair value = mid price (rolling SMA-3 of mid)
- Market make: passive quote ±1 tick from fair, qty 5 units each side
- No IV computation needed

**Tier B — Active IV Scalping (VEV_5000 through VEV_5500): 6 strikes**
1. Get spot price S = VEV mid price
2. For each strike K, compute mid price from order book
3. Compute IV = `_implied_vol(S, K, TTE_years, mid)` — skip if None or S not available
4. Compute moneyness `m = ln(K/S) / sqrt(TTE_days)` (TTE_days for smile normalization, keep consistent)
5. After warmup (50+ IV readings per strike), fit quadratic smile over current-tick IVs: `IV = a*m² + b*m + c`
6. Fair IV for each strike = `a*m² + b*m + c`
7. Fair price = `_bs_call(S, K, TTE_years, fair_iv)`
8. Trade signal:
   - If `mid < fair_price - THRESH` (cheap): buy up to `pos_limit_per_strike - pos`
   - If `mid > fair_price + THRESH` (expensive): sell down to `-(pos_limit_per_strike - |pos|)`
   - `THRESH = 1.5` ticks (empirical; tune via backtest)
   - `pos_limit_per_strike = 50` (conservative; avoids large unhedged delta)
9. Also do passive market making: quote ±1 tick from fair price (qty 5)

**Tier C — Deep OTM (VEV_6000, VEV_6500): price stuck at 0.5**
- Skip (no edge, prices can only go up, not worth the inventory risk)

### State in `traderData` (JSON)

```
{
  "hp_data": {"bid_hist": [...], "ask_hist": [...]},
  "vev_data": {"bid_hist": [...], "ask_hist": [...]},
  "opt_data": {
    "day_count": int,
    "prev_ts": int,
    "iv_hist": {"VEV_5000": [float, ...], ...},   # rolling 50
    "itm_mid_hist": {"VEV_4000": [...], "VEV_4500": [...]}  # rolling 3
  }
}
```

### Quadratic Fitting (3×3 normal equations, pure Python)

With N IVs computed at moneynesses `m_i`:
```
| Σm⁴  Σm³  Σm²  | |a|   |Σm²·iv|
| Σm³  Σm²  Σm   | |b| = |Σm·iv |
| Σm²  Σm   N    | |c|   |Σiv   |
```
Solve via Gaussian elimination (3×3 is trivial, hand-code). Fall back to flat constant c = mean(iv) if matrix is singular or fewer than 3 strikes available.

## File Architecture

All logic in `rounds/round3/algo/trader.py` as a single `Trader` class:

```
class Trader:
    run(state)                  ← orchestrates all strategies
    hydrogel(state, shared)     ← HYDROGEL_PACK
    vev_spot(state, shared)     ← VELVETFRUIT_EXTRACT
    vev_options(state, shared)  ← all 10 vouchers + helpers embedded
    _norm_cdf(x)                ← static helper
    _bs_call(S,K,T,sigma)       ← static helper
    _implied_vol(S,K,T,price)   ← static helper
    _fit_quadratic(xs,ys)       ← static helper  
    _solve3x3(A,b)              ← static helper (Gaussian elim)
```

Logger class (same as `trader.py` root) for visualization compatibility.

## Backtesting Plan

Run via:
```bash
python3 -m prosperity4bt cli rounds/round3/algo/trader.py 3
```

Tunable parameters to sweep after initial implementation:
- `THRESH` (1.0–3.0): vol smile deviation threshold in price ticks
- `pos_limit_per_strike` (20–100): per-strike position cap
- `IV_WINDOW` (20–100): rolling IV window for warmup check
- `HYDROGEL_QUOTE_LIM` (5–20): passive quote size

## Verification

1. Run backtest on round 3 data (days 0, 1, 2) with `--print` to inspect per-tick orders
2. Check: does IV computation produce sensible values (~20–30% annualized)?
3. Check: do smile fits yield reasonable quadratics (small curvature)?
4. Check: are trades firing on both sides (not directionally biased)?
5. Check: position limits respected for all 12 products
6. Copy to `trader.py` and run full 3-day backtest with `--merge-pnl`
7. Iterate THRESH and pos_limit_per_strike for best PnL
