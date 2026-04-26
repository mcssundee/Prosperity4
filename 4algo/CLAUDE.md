
The products are the same as in Round 3 (HYDROGEL_PACK, VELVETFRUIT_EXTRACT, and 10 VELVETFRUIT_EXTRACT_VOUCHER options), but now you have counterparty information available. That is, you can identify every other participant in the market and study their behavior. use self.buyer and self.seller fields in class Trader

Position limits:
- HYDROGEL_PACK: 200
- VELVETFRUIT_EXTRACT: 200
- VELVETFRUIT_EXTRACT_VOUCHER: 300 for each of the 10 vouchers.

---

## Session findings (2026-04-26 / 2026-04-27)

### Visualiser
- Built `4algo/vis.py` — Dash app on port 8050. Run: `python3 4algo/vis.py`
- Sections: main price/trade chart, PnL curves, trader deep dive (PnL + spread/OBI/momentum/position/informed overlays), shadow strategy simulator, HYDROGEL ACF + rolling ACF heatmap, HYDROGEL price structure
- Info boxes (ⓘ) on every section explain what each metric means
- Backtest PnL curves: run `python3 4algo/backtest_curves.py`

### HYDROGEL_PACK market structure
- **Only two participants: Mark 14 and Mark 38.** Every HYDROGEL trade is between them.
- Mark 14 is profitable; Mark 38 loses. Mark 14 earns the spread passively as a market maker.
- **No relationship with VELVETFRUIT_EXTRACT** — R²≈0, no lead-lag. Products are independent.
- **No robust autocorrelation in HYDROGEL returns** — rolling ACF heatmap mostly white. Point-in-time signals are regime-specific noise.
- **Price mean-reverts around ~10,000.** Range 9,900–10,080. Deviation σ≈5–7, Gaussian, tails at ±20. Bid-ask spread almost always exactly **16 points**.
- **No taker alpha.** Must use maker strategy. Mark 38's problem = adverse selection + no inventory skew.

### HYDROGEL_PACK strategy — current params in `trader.py` and `4algo/trader_hydrogel.py`
- `fv_window = 20` — rolling mean of last 20 mids (= 2,000 ticks). **Critical: longer windows lag trends → systematic inventory drift.**
- `half_spread = 4` — quote at fair ± 4
- `flat_thr = 120` — quote both sides while |pos| < 120; go one-sided beyond that
- `unwind_thr = 175` — actively cross spread only when |pos| > 175 (near limit)
- `quote_size = 50` — units per price level
- Two price levels per side: fair±4 and fair±6, so up to 100 units per side when flat
- Passive quote caps: bid never crosses best_ask, ask never crosses best_bid
- No inventory skew formula — pure one-sided quoting handles position management

### Key lessons
- `fv_window=100` → lagged fair value → systematic short drift → large MTM losses. `fv_window=20` fixed this.
- Local backtester double-fills passive orders (fills both sides of market trades). **Do not trust local backtest for MM strategy quality — use online backtester.**
- Online backtester confirmed strategy is profitable (Day 3 only run: +223 PnL with conservative params).
- VELVETFRUIT and VEV options strategies are just accumulating long positions, not genuine MM. Their "PnL" is mostly MTM of large held positions — unreliable.
- Copying Mark 14 (aggressive taker) doesn't work — he earns spread passively, you pay it as a taker.
- `import os` is forbidden by the competition platform — never add it to trader.py.

### Separate trader files in `4algo/`
- `trader_hydrogel.py` — HYDROGEL only (submit this to test in isolation)
- `trader_velvetfruit.py` — VELVETFRUIT only
- `trader_options.py` — VEV vouchers only

### TODO next session
- Submit updated `trader_hydrogel.py` (quote_size=50, flat_thr=120) to online backtester — check curve shape and whether position hits the 175 unwind threshold
- Fix VELVETFRUIT strategy: apply same approach as HYDROGEL (dynamic fair value + one-sided inventory quoting, no directional accumulation)
- Fix VEV options: same problem — accumulates longs, not genuine MM
- Once all three are fixed, combine back into `trader.py` and run full 3-day online backtest
