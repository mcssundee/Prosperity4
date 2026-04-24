# Competitor 2 — CMU Physics

**Source**: https://github.com/chrispyroberts/imc-prosperity-3
**Finish**: Rank 7 Global, Rank 1 USA
**Team**: Chris Roberts, Nirav Koley, Aditya Dabeer, Timur Takhtarov (Carnegie Mellon)

---

## Round 1

### Rainforest Resin
- Fair value fixed at 10,000
- Market take when bids > 10,000 or asks < 10,000
- Market make inside spread; exploit standing orders at fair value to balance inventory

### Kelp
- Identified a persistent market maker whose mid-price defined real-time fair value
- Same MM/take strategy as Resin; no directional bias

### Squid Ink
- Tested rolling z-scores, volatility breakouts, MACD — no consistent edge
- Post-round fix: 10% position allocation; spike detection: if rolling std of price diffs > 20, enter full position opposite to recent move

### Manual Round 1
- BFS over currency exchange paths (identical to LeetCode 3387)

---

## Round 2

### Basket Strategy
- Rolling z-score of premium, entry/exit at z = ±20, window = 30
- When z > 20: short basket, long constituents. Vice versa.
- Key innovation: trade the **spread of spreads** (difference between Basket 1 and Basket 2 premiums) to solve position limit constraints
- Allocation: 100% Basket 1 limit, 60% Basket 2 via differential spread, 32% Basket 2 standalone z-score, 8% market making

### Manual Round 2 — Containers
- Built Monte Carlo simulation to Nash equilibrium
- Priors: 15% Nash, 50% random, 20% "nice numbers," 10% misread prompt, 5% flawed MC
- Chose 80× crate — underperformed

---

## Round 3

### Vol Smile Approach
- Moneyness: `m_t = log(K / S_t) / sqrt(TTE)`
- Fitted quadratic: `v_t = a·m_t² + b·m_t + c`
- Aggressive market maker based on fitted IV
- Delta-hedged every timestamp
- Position cap: 80 per voucher (to guarantee full hedge with 400 VR position limit)

### Post-round Issues (fell from 7th to 241st)
1. Jmerle's visualizer caused AWS Lambda memory restarts, wiping rolling windows mid-trade
2. Quadratic fit stopped working on submission day (IV regime shifted) — fix: use rolling window of mid IV instead of fitted parabola
3. Delta hedging cost 40k+ in spread costs — decision: go unhedged (average delta ~160 VR; max loss per step ~16k vs. 40k hedge savings)

---

## Round 4

### Macarons
- Recognized as identical to "Orchids" from Prosperity 2
- Break-even: `conversion_ask + import_tariff + transport_fee`
- Identified aggressive buyer bot near Pristine Island mid-price
- Placed sell orders near mid-price (above break-even), immediately converted after fills
- Post-round: switched to 30-unit quotes to double throughput

### Manual Round 4 — Suitcases
- Updated priors from Round 2 actuals: 50–60% Nash, 15% "nice numbers," 10–15% random
- Chose suitcases 83 and 47
- Best round: moved from 241st back to 8th

---

## Round 5

### Olivia Copy-Trading
- Directly identified Olivia on Squid Ink, Croissants, Kelp
- Squid Ink: market make/take until Olivia's signal fires, then follow for rest of day
- Croissants YOLO: max 250 direct + ~800 via baskets = 1,050 effective Croissant exposure
- Basket adjustment: only take basket trades in same direction as Olivia's Croissant signal

### Position Math
- Worst-case Croissant swing = 40 SeaShells → 800 × 40 = 32k downside
- Best day: 120 SeaShell spread → 800 × 120 = 96k upside

### Manual Round 5
- Used `cvxpy` convex optimization for portfolio allocation
- Quadratic fee structure: `Fee(x) = 120x²`
- Made 138,274 SeaShells on manual

---

## Meta-Insights
- Spread of spreads approach elegantly solves position limit constraints on multi-leg ETF arb
- Avoid delta hedging options if hedge cost exceeds expected gamma profit
- Use rolling IV window rather than fitted parabola for robustness to regime shifts
- Jmerle's backtester has Lambda memory restart bug — wipes rolling state mid-backtest
