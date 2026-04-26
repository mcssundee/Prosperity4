
The products are the same as in Round 3 (HYDROGEL_PACK, VELVETFRUIT_EXTRACT, and 10 VELVETFRUIT_EXTRACT_VOUCHER options), but now you have counterparty information available. That is, you can identify every other participant in the market and study their behavior. use self.buyer and self.seller fields in class Trader

Position limits:
- HYDROGEL_PACK: 200
- VELVETFRUIT_EXTRACT: 200
- VELVETFRUIT_EXTRACT_VOUCHER: 300 for each of the 10 vouchers.

---

## Session findings (2026-04-26)

### Visualiser
- Built `4algo/vis.py` — Dash app on port 8050. Run: `python3 4algo/vis.py`
- Sections: main price/trade chart, PnL curves, trader deep dive (PnL + spread/OBI/momentum/position/informed overlays), shadow strategy simulator, HYDROGEL ACF + rolling ACF heatmap, HYDROGEL price structure
- Info boxes (ⓘ) on every section explain what each metric means

### HYDROGEL_PACK market structure
- **Only two participants: Mark 14 and Mark 38.** They are mirror images — every HYDROGEL trade is between them.
- Mark 14 is profitable; Mark 38 loses. Mark 14 earns the spread as a market maker.
- **No relationship with VELVETFRUIT_EXTRACT** — R²≈0, no lead-lag at any lag. Confirmed via CCF on returns. These products are independent.
- **No robust autocorrelation in HYDROGEL returns** — rolling ACF heatmap is mostly white. Signals seen in point-in-time ACF (e.g. lag 38-39 positive, lag 40 negative) are regime-specific, not structural.
- **Price is mean-reverting around ~10,000.** Mid price range: 9,900–10,080. Deviation from rolling mean is nearly perfectly Gaussian with σ≈5–7, zero mean, tails at ±20. Bid-ask spread is almost always exactly **16 points**.
- **Conclusion:** No taker strategy viable (no price signal). Must use **maker strategy** — post quotes around rolling fair value, capture spread passively.
- Mark 38's losing problem = adverse selection + no inventory skew. This is solvable.

### HYDROGEL_PACK strategy (implemented in `trader.py`)
Current params (tuned via backtest sweep — +369k over 3 days, position stays ±26):
- `fv_window = 20` — rolling mean of last 20 mid prices (= 2,000 ticks). **Critical: longer windows lag price trends and cause systematic inventory drift.**
- `half_spread = 4` — quote at fair ± 4
- `skew_rate = 0.40` — shift both quotes by `skew_rate × position` against inventory
- `unwind_thr = 40` — actively cross spread if |pos| > 40
- `quote_size = 15` — units per passive quote
- Passive quote caps: bid never crosses best_ask, ask never crosses best_bid
- Active taking only when |pos| < unwind_thr

Key insight that fixed the strategy: `fv_window=100` caused quotes to lag price by 10,000 ticks → systematic short accumulation → large MTM losses. `fv_window=20` tracks current mid accurately.

### Shadow strategy finding
- Copying Mark 14's trades (aggressive, one tick later) loses money because Mark 14 earns the spread **passively** — you can't replicate that as an aggressive follower. You pay the spread every trade.

### Next steps for HYDROGEL
- Consider whether quote_size can be increased (currently capped at 15)
- Investigate whether Mark 38's quoting behaviour has patterns (quote staleness window)
- The strategy is maker-only — no taker alpha found

### Other products (not investigated today)
- VELVETFRUIT_EXTRACT: existing SMA-5 MM strategy in trader.py
- VEV options: existing BS-based strategy in trader.py
- These were not touched today
