# Round 2 — Post-Round Hindsight Notes

## Products
- `ASH_COATED_OSMIUM` (limit 80) — stable mean-reverting product, wide spread
- `INTARIAN_PEPPER_ROOT` (limit 80) — trending/momentum product with early sweep opportunity

## What the Baseline Missed

### ASH_COATED_OSMIUM
- **Wall Mid fair value** (Frankfurt Hedgehogs, Rank 2): Use the lowest bid-wall price and
  highest ask-wall price as fair value — far more stable than SMA of best bid/ask.
- **Active taking threshold**: Relax buy threshold by +1 tick when position < −15 to flatten
  inventory faster. Baseline had this but capped active taking at pos ≤ 60 instead of 80.
- **Full position limit usage**: Baseline capped active orders at ±60 but limit is 80.
  Passive quotes should fill remaining capacity up to ±80.

### INTARIAN_PEPPER_ROOT
- **Informed trader signal**: Watch for a bot (similar to "Olivia" in Prosperity 3) that
  consistently buys at daily lows and sells at daily highs in fixed lot sizes. If present,
  copy-trade it aggressively instead of using a trailing stop.
- **Conversion limit**: The sweep-to-76 approach leaves 4 units of capacity unused.
  Should sweep to full 80.
- **Earlier sweep trigger**: After timestamp 2000 is conservative. Data suggests earlier
  entry (timestamp 1000–1500) captures more of the move.

## Optimal PnL Ceiling
- Baseline achieves ~298,198 across 3 days
- Optimal with wall mid + full position usage estimated: 310,000–320,000
- If informed trader signal exists and is exploited: potentially 350,000+

## References
- Frankfurt Hedgehogs write-up: Wall Mid concept, Olivia signal detection
- CMU Physics write-up: Spread of spreads, position limit management
