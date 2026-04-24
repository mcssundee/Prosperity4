Round 3 – GOAT (Great Orbital Ascension Trials)
Leaderboard resets. PnL starts at 0.
Algorithmic Trading
Trade three products: HYDROGEL_PACK, VELVETFRUIT_EXTRACT, and 10 VELVETFRUIT_EXTRACT_VOUCHER variants.
Position limits:

HYDROGEL_PACK: 200
VELVETFRUIT_EXTRACT: 200
VELVETFRUIT_EXTRACT_VOUCHER (each): 300

Vouchers (VEV_<strike>): options on VELVETFRUIT_EXTRACT. Strikes: 4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500.

TTE = 7d in Round 1, decrements by 1 each round → TTE = 5d in Round 3
Historical data: TTE=8d (tutorial), TTE=7d (R1), TTE=6d (R2)


Manual Trading – Celestial Gardeners' Guild
Goal: Buy Ornamental Bio-Pods cheap; they auto-sell at 920 next round.
Counterparty reserve prices: Uniform distribution, 670–920 in increments of 5.
Submit 2 bids:

Bid 1: Trades with anyone whose reserve price < bid 1 (you pay bid 1).
Bid 2:

If bid 2 > reserve price and bid 2 ≥ avg of all players' bid 2 → trade at bid 2.
If bid 2 > reserve price but bid 2 < avg bid 2 → trade occurs but PnL penalised by:



(920−avg_b2920−b2)3\left(\frac{920 - \text{avg\_b2}}{920 - b2}\right)^3(920−b2920−avg_b2​)3
Resubmit anytime; last submission counts when round ends.