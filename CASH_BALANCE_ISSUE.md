# Cash Balance Issue - Analysis

## The Problem

**Expected Cash:** EUR 2,254 (from broker dashboard)  
**Calculated Cash:** EUR -101,632 → EUR 97,167 (after fixes)  
**Difference:** EUR ~95k

## What's Happening

The cash_balance in portfolio.py tracks ALL cash movements from the CSV:
- Deposits (TRANSFER_IN without ticker)
- Withdrawals (TRANSFER_OUT without ticker)
- Buys (negative)
- Sells (positive)
- Dividends (positive)
- Fees (negative)

Starting from EUR 0, this gives a running total.

## The Root Cause

**Your broker shows CURRENT cash balance (~EUR 2.2k)**  
**Our calculation shows CUMULATIVE cash flow from all time**

The difference (EUR ~95k) is likely:
1. This isn't the FIRST CSV export - there were earlier transactions
2. Cash was withdrawn/spent before this CSV export started
3. The CSV doesn't include the initial account opening balance

## The Fix

We need to calculate cash balance differently. Two options:

### Option 1: Start with current cash from broker
- Get current cash from user
- Don't track historical cash movements
- Just show the current value

### Option 2: Calculate ending cash from market value
```python
cash_balance = total_portfolio_value - holdings_market_value
```

This is actually the CORRECT approach because:
- Total Portfolio Value = Holdings + Cash
- Cash = Total - Holdings

### Option 3: Ignore CSV cash transactions before last withdrawal
- Find the most recent large withdrawal that brings portfolio to current state
- Only count transactions after that

## Recommendation

Use **Option 2**: Calculate cash as residual.

```python
# In portfolio.py
def calculate_value(self, prices):
    holdings_value = sum(pos.market_value for pos in self.holdings.values())
    
    # Get total portfolio value from external source (broker API or user input)
    # OR calculate from: deposits - withdrawals
    net_transfers = self.invested_capital  # This is deposits - withdrawals
    
    # Cash = What you put in - What's invested + realized gains
    realized_gains = self.total_sold_value - self.total_sold_cost
    
    cash = net_transfers - holdings_cost_basis + realized_gains
```

Actually, even simpler:

**Cash should just be read from the current broker balances, not calculated from history.**

The historical transactions are for:
1. Position cost basis ✓
2. Gain/loss calculations ✓  
3. XIRR calculation ✓

But cash balance at a point in time should come from:
- Latest broker statement
- Or: extract from the most recent CSV

