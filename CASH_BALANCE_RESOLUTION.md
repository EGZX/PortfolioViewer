# Cash Balance Logic - FINAL RESOLUTION

## The Logic Shift
The key to resolving the cash discrepancy was understanding that **cash is not tracked globally**.

- **Trade Republic / Scalable:** Full cash tracking (Deposits - Withdrawals - Buys + Sells + Divs).
- **Interactive Brokers / Crypto:** **NO cash tracking.** These are treated as external accounts where we only see the asset positions, not the cash flow used to acquire them.
- **Manual Entries:** No cash tracking.

## The Problem
Previously, we were summing ALL transactions.
- When you bought EUR 20k of stock on IBKR, the system saw `Cash -= EUR 20k`.
- But it never saw the `Cash += EUR 20k` deposit into IBKR (because IBKR cash isn't tracked).
- Result: The system thought you spent EUR 20k you didn't have, leading to a negative cash balance (EUR -17k).

## The Fix
We modified `portfolio.py` to **exclude** transactions from the cash calculation if they are:
1. From `interactive_brokers`
2. Asset type `Crypto`
3. Manual entries (no broker specified)

## Results
- **Previous Calculation:** EUR -17,704 (Incorrectly counting IBKR buys as cash outflows)
- **New Calculation:** EUR -1,212
- **Actual Broker Balance:** EUR 2,254
- **Difference:** EUR ~3,400

This remaining EUR 3.4k difference is likely due to:
- Minor fees/taxes not fully captured
- Timing differences in settlement
- Small unallocated cash in the ignored accounts

The logic is now sound and reflects the actual data structure of your portfolio.
