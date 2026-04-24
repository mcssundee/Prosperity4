# Competitor 3 — Alpha Animals (UC San Diego)

**Source**: https://github.com/CarterT27/imc-prosperity-3
**Finish**: Rank 9 Global, Rank 2 USA
**Team**: Carter Tran, Kenji Gunawan, Evan Ai, Marc Boudames, Sancho Syquia (UC San Diego)
**Final Score**: 1,190,077 SeaShells

---

## Architecture
- Monolithic `trader.py` (~700+ lines), single `Trader` class
- State persisted via `jsonpickle`
- Black-Scholes class with implied volatility binary search (bisection, 200 iterations, tolerance 1e-10)
- `active_products` dict to toggle strategies on/off

---

## Round 1

### Rainforest Resin
- Fair value hardcoded at 10,000
- Take width 0.3, make width 3.0

### Kelp
- Fair value = (best_bid + best_ask) / 2
- Make width 8.0, take width 1.0

### Squid Ink
- Volatility-spike mean-reversion
- Parameters: `volatility_threshold = 3.0` std devs over 10-timestamp window, `mean_window = 30`
- When spike detected, enter opposite direction; close after `max_position_time = 5` timestamps or reversal
- Allocation: 10% of position limit

---

## Round 2

### Basket Statistical Arbitrage
- PB1 synthetic: `6·C + 3·J + 1·D + intercept(−57.71)`
- PB2 synthetic: `4·C + 2·J + intercept(−22.59)`
- Signal: trade basket toward its synthetic when they diverge
- Note: had position limit overrun bugs — strategy did not fully work

---

## Round 3

### Black-Scholes Options Pricing
- Full BS with IV binary search (bisection, 200 iterations, tolerance 1e-10)
- Rolling volatility window; priced vouchers using rolling IV
- Looked for arbitrage between strikes: `zscore_threshold = 1.8`, `volatility_window = 30`
- Volcanic Rock: used average IV from all vouchers to determine fair rock price; directional when deviation significant

### Accidental Win
- A bug caused the algo to short Volcanic Rock at max position the entire day — accidentally worked and vaulted them to 2nd globally

---

## Round 4

### Magnificent Macarons — Cross-market Arbitrage
- Break-even: `sell_local_breakeven = conversion_ask + import_tariff + transport_fee`
- Normal sunlight: buy locally if below foreign ask (after fees); sell locally if above foreign bid
- Low sunlight (`sunlight < CSI_THRESHOLD = 0`): accumulate long, avoid exports
- Position skew factor: at >50% of limit, reduce orders in that direction (min 20% size)
- Note: could not get working strategy by deadline — disabled Volcanic Rock trading

---

## Round 5

### Olivia Identification Method
- Calculated % of "good trades" (buy low/sell high relative to future price) per trader over rolling windows
- Systematically identified Olivia as the insider across multiple products

### Copy-Trading (Squid Ink + Croissants)
- When Olivia buys: buy up to position limit at best ask
- When Olivia sells: sell up to position limit at best bid
- Did NOT copy on Jams or Djembes
- Scaled order sizes by current inventory ratio to avoid overexposure

### Macarons Fix
- Ignored sunlight index entirely (potentially overfit)
- Focused solely on statistical arbitrage (convert-based)

---

## Meta-Insights
- Binary search for IV is robust and fast (200 iterations, 1e-10 tolerance)
- Systematic "good trade %" analysis is a clean, generalizable method to identify informed traders
- Sunlight-based Macaron signals may be overfit — simpler convert-based arb is more robust
- Toggling strategies on/off via `active_products` dict is useful for debugging in production
