# **Manual trading challenge: “The Celestial Gardeners’ Guild”**

You trade against a number of counterparties that all have a **reserve price** ranging between **670** and **920**. On the next trading day, you’re able to sell all the product for a fair price, **920**.

The distribution of the bids is **uniformly distributed** at **increments of 5** between **670** and **920**. 

<aside>
📃

**Example**: counterparties may have reserve prices at 675 and 680, but not at 676, 677, 678, 679, etc..

</aside>

You may submit **two bids**. If the first bid is **higher** than the reserve price, they trade with you at your first bid. If your second bid is **higher** than the reserve price of a counterparty and **higher** than the mean of second bids of all players you trade at your second bid. If your second bid is **higher** than the reserve price, but **lower** than the mean of second bids of all players, the chance of a trade rapidly decreases: you will trade at your second bid **but** your PNL is penalised by 

$$
\left(\frac{920 - \text{avg\_b2}}{920 - b2}\right)^3
$$

## **Submit your orders**

Submit your two bids directly in the Manual Challenge Overview window and click the “Submit” button. You can re-submit new bids until the end of the trading round. When the round ends, the last submitted bids will be offered to the members of the Celestial Gardeners' Guild.

Each counterparty is willing to trade with you at most once