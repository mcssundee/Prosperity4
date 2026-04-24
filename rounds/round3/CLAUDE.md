# Trading Strategy Reference

## ORCHIDS — Cross-Exchange Arbitrage

**Core insight:** Local market has a persistent hidden buyer. Sell orders placed slightly above best local bid fill immediately and in full. Pure arbitrage loop: sell locally, source via South Archipelago at lower implied cost.

**Do not trade directionally** on sunlight, humidity, tariffs, or shipping — tested thoroughly, no robust signal found.

**Three-layer strategy:**
1. **Pure arb taking** — at each step, compute implied foreign bid/ask after fees. If local offers better price, take immediately.
2. **Arb market-making** — post local quotes only when profitable after conversion costs. Objective: maximize `edge × execution_probability`.
3. **Adaptive quoting** — monitor realized fill volume; if fills drop below threshold, reduce edge to find more competitive level. Fixed rule: sell around `foreign_ask - 2` is a good baseline.

**Conversion math:**
- Local sell break-even = `external_ask + import_tariff + transport_fee`
- Only trade when local vs. foreign deviation exceeds this

---

## GIFT_BASKET / PICNIC_BASKETs — Basket Spread Arb

**Compositions:**
- `GIFT_BASKET = 4×CHOCOLATE + 6×STRAWBERRIES + 1×ROSE`
- `PICNIC_BASKET1 = 6×CROISSANTS + 3×JAMS + 1×DJEMBE`
- `PICNIC_BASKET2 = 4×CROISSANTS + 2×JAMS`

**Core insight:** Basket trades at a persistent premium over synthetic value. Deviations mean-revert. The basket is the noise; constituents are the fundamentals. Gift Basket premium ~370 historically.

**Signal:**
```
spread = basket_price - synthetic_price
z_score = (spread - long_run_premium_mean) / rolling_std(spread, short_window)
```
- `z > threshold` → sell the spread (basket rich)
- `z < -threshold` → buy the spread (basket cheap)

Use **short rolling window** for std — sharpens signal near turning points.

**Hedging:** Trade-off between full hedge (purer, more legs/costs) and unhedged (simpler, directional risk). Often partial hedge (e.g. 50%) is optimal. When position limits prevent full hedge, accept unhedged residual.

**Dual-basket capital allocation (BASKET1 + BASKET2 sharing constituents):**
1. Trade relative premium: `premium_spread = B1_premium - B2_premium`, z-score this, trade as relative value.
2. Use remaining risk budget for standalone basket trades — allocate to whichever has strongest deviation.
3. Leftover capacity → light market making on wide basket spreads.

**Execution:** When z-score is extreme, cross the market immediately — missing the trade is more expensive than the spread cost. Exit once spread reverts to fair, not necessarily all the way to opposite threshold.

---

## VOLCANIC ROCK VOUCHERS — Options / IV Mean Reversion

**Structure:** European call options on Volcanic Rock. Strikes 9500–10500.

**Core strategy:** Black-Scholes IV scalping.
1. Back out implied vol from observed market prices.
2. Fit volatility smile vs. moneyness (quadratic) for multi-strike products.
3. Reprice each voucher using fitted IV.
4. Buy when market price < theoretical; sell when market price > theoretical.
5. Delta-hedge with underlying to isolate vol exposure.

**IV reference:** Coconut Coupon IV oscillated ~16%. Use rolling mean as fair IV anchor.

**Delta hedging constraint:** If position limits prevent full hedge, cap option position size so the hedge is clean. Do NOT oversize options and patch with cross-strike hedges under time pressure.

**Strike selection by moneyness:**
- Deep ITM (9500, 9750) → co-move with underlying → use mean-reversion on underlying instead of IV arb
- ATM (10000) → IV z-score arb
- OTM/deep OTM (10250+) → remove if likely to expire worthless

**Additional edges:**
- **Gamma scalping:** Buy options, dynamically delta-rehedge; works when realized vol > implied vol
- **Underlying mean reversion:** Separate model, small overlay only — negative autocorrelation in returns

**Key lesson:** Unhedged delta risk killed performance in live trading despite good backtests. Prioritize lower variance if near top of leaderboard.

---

## COCONUTS / ROSES — Prior-Year Signal Arbitrage

**Discovery:** Prior competition data (public on GitHub) shows near-perfect predictive relationships:
- Last year's Diving Gear (×3) → this year's Roses, R² ≈ 0.99
- Last year's Coconuts (×1.25) → this year's Coconuts, R² ≈ 0.99

**Execution — Dynamic Programming:** Given a known future price path, use DP to find optimal trade sequence under constraints (spread costs, volume limits, position limits).

Example with position limit 2, volume cap 2/step:
- Path: 8→7→12→10
- Naïve optimum: sell 2 → buy 4 → sell 4 = PnL 16 (infeasible if volume capped)
- DP optimum: buy 2 → buy 2 → sell 2 = PnL 14

**Inputs to DP:** predictor price series, average spread estimate, executable volume as fraction of position limit.

**Applied to:** Roses, Coconuts, Gift Baskets → ~2.1M seashells (highest of any team).

---

## MAGNIFICENT MACARONS — Location Arbitrage + Hidden Taker

**Do not trade directionally** on sunlight/sugar prices — arb edge dominates.

**Break-even:**
- `local_sell_break_even = external_ask + import_tariff + transport_fee`

**Hidden taker discovery:** Local sell orders placed at `int(externalBid + 0.5)` fill reliably above the visible best bid. A hidden participant buys aggressively at this level.

**Strategy:**
- Quote sells locally at `int(externalBid + 0.5)`
- On fill, immediately convert/unwind externally
- Storage cost = 0.1/timestamp → minimize inventory duration
- Conservative sizing: 10 units/step (conversion limit); larger sizes feasible with gradual conversion

**One-sided only:** Export tariffs make the reverse (buy local, sell external) rarely worthwhile.

---

## OLIVIA — Informed Trader Signal

**Identification:** Olivia consistently buys near local lows, sells near local highs across Squid Ink, Croissants, Kelp.

**Squid Ink:** Run existing market-making until Olivia trades → treat as regime shift → follow her direction for rest of day.

**Croissants + Baskets interaction:**
- Croissants ~50% of basket value → running basket arb against Olivia's direction cancels the signal
- Direct Croissant limit: 250; effective basket exposure: ~1050 Croissant-equivalent
- On strong days (120 SeaShell high-low move), extra 800 Croissant exposure adds ~96k
- Hedge remaining basket legs (Jams, Djembes) as much as position limits allow
- Accept ~30 Jam residual — expected gain from Croissant signal exceeds Jam downside

**Premium risk:** Basket premium change is approximately stationary → expected premium P&L ≈ 0; worst case ~300/basket (45k aggregate). Probabilistically acceptable if Olivia signal isn't correlated with premium extrema.

**Execution edge:** Don't just cross best bid/ask — place layered limit orders across multiple levels weighted by confidence and historical fill behavior.

**Conservative mode** (when holding large lead): half-hedge basket exposure, reduce mean-reversion sleeve.

---

## PINA COLADAS / COCONUTS — Pair Trading

**Spread:** `Pina_Colada - (15/8) × Coconut`

Trade deviations from historical spread mean. Mean reversion consistently outperformed momentum in backtests.

---

## Round-by-Round Product Summary

| Round | New Products | Key Strategy |
|-------|-------------|-------------|
| 1 | Rainforest Resin, Kelp, Squid Ink | MM on Resin (~10k fair value); adaptive MM on Kelp; directional pressure signal on Squid Ink |
| 2 | Croissants, Jams, Djembes, Basket1, Basket2 | Basket synthetic arb; z-score on Jams; skip standalone Croissants/Djembes |
| 3 | Volcanic Rock + 5 vouchers | IV z-score arb on ATM vouchers; dynamic MM on underlying |
| 4 | Magnificent Macarons | Hidden taker arb + conversion |
| 5 | (none) + trader IDs revealed | Olivia signal extraction; layered limit orders for execution edge |

---

## General Principles

- **Market structure beats prediction.** External variables (sunlight, sugar, humidity) look useful but rarely produce robust live alpha. The dominant edge is almost always in microstructure and execution.
- **Overfitting risk:** Keep core models structurally motivated. Z-score is an entry-timing tool, not the strategy itself.
- **Residual MM:** When position limits prevent full arb deployment, use leftover capacity for passive liquidity provision on wide spreads — incremental PnL, low variance.
- **Rank preservation:** When holding a lead, reduce variance deliberately — lower hedge ratios, smaller option positions, tighter inventory limits.