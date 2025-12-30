# Moving Average Cost Basis - Implementation Analysis

## 📚 Theory: Moving Average Cost Method

### Correct Formula:
```
When BUY:
  new_shares = old_shares + buy_shares
  new_cost_basis = old_cost_basis + buy_cost
  new_avg = new_cost_basis / new_shares

When SELL:
  avg_cost_per_share = current_cost_basis / current_shares
  cost_of_sold = avg_cost_per_share × sold_shares
  new_cost_basis = current_cost_basis - cost_of_sold
  new_shares = current_shares - sold_shares
  new_avg = new_cost_basis / new_shares (if new_shares > 0)
```

### Example Path-Dependent Calculation:

```
Initial: 0 shares, €0 cost basis

1. BUY 10 @ €100
   cost_basis = 0 + (10 × 100) = €1,000
   shares = 10
   avg = €1,000 / 10 = €100/share ✓

2. SELL 5 (using moving avg)
   avg = €1,000 / 10 = €100/share
   cost_of_sold = 5 × €100 = €500
   cost_basis = €1,000 - €500 = €500
   shares = 5
   avg = €500 / 5 = €100/share ✓

3. BUY 10 @ €200
   cost_basis = €500 + (10 × €200) = €2,500
   shares = 5 + 10 = 15
   avg = €2,500 / 15 = €166.67/share ✓

4. SELL 8
   avg = €2,500 / 15 = €166.67/share
   cost_of_sold = 8 × €166.67 = €1,333.33
   cost_basis = €2,500 - €1,333.33 = €1,166.67
   shares = 7
   avg = €1,166.67 / 7 = €166.67/share ✓
```

---

## 🔍 Current Implementation Review

### Code Location: `calculators/portfolio.py` lines 130-170

```python
# INCREASE POSITION (BUY)
if t.type in [TransactionType.BUY, TransactionType.TRANSFER_IN, TransactionType.STOCK_DIVIDEND]:
    pos.shares += t.shares
    amt = abs(amount_eur)  # ← amount_eur = t.total * t.fx_rate
    if t.type == TransactionType.STOCK_DIVIDEND:
        amt = 0
    pos.cost_basis += amt  # ← ADDS to cost basis ✓

# DECREASE POSITION (SELL)
elif t.type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
    if pos.shares > 0:
        cost_per_share = pos.cost_basis / pos.shares  # ← Calculate avg ✓
        shares_to_remove = min(t.shares, pos.shares)
        sold_cost = cost_per_share * shares_to_remove  # ← Pro-rata ✓
        pos.cost_basis -= sold_cost  # ← REDUCES cost basis ✓
    
    pos.shares -= t.shares
```

### ✅ Algorithm is CORRECT!

The implementation follows moving average cost method properly.

---

## 🐛 Potential Issues

### Issue 1: Transaction Ordering
**Location:** Line 42 in `portfolio.py`
```python
self.transactions = sorted(transactions, key=lambda t: t.date)
```
✅ **CORRECT** - Transactions are sorted by date

### Issue 2: Cost Basis Sign Convention
**Question:** Is `amount_eur` calculated correctly?

Line 57:
```python
amount_eur = t.total * t.fx_rate
```

For a BUY transaction:
- `t.total` should be NEGATIVE (cash out)
- Line 142: `amt = abs(amount_eur)` converts to positive
- ✅ **CORRECT**

For a SELL transaction:
- `t.total` should be POSITIVE (cash in)
- But we don't use `amount_eur` in SELL, we use `cost_per_share`
- ✅ **CORRECT**

### Issue 3: TRANSFER_IN Handling
**Line 131:** `TRANSFER_IN` is treated like a BUY

**Question:** When you transfer IN stocks from another broker, what should be the cost basis?

Current logic:
```python
amt = abs(amount_eur)  # From transaction total
pos.cost_basis += amt
```

**PROBLEM:** If `TRANSFER_IN` has `total=0` (no cash flow), then `amt=0`, and cost basis DOESN'T increase!

**Example:**
- You transfer 10 shares from Broker A to Broker B
- CSV shows: `TRANSFER_IN, 10 shares, price=€0, total=€0`
- Code adds €0 to cost_basis → **WRONG!**

### Issue 4: Fee Handling
**Line 142:** Uses `abs(amount_eur)` which is `abs(t.total * t.fx_rate)`

**Question:** Does `t.total` include or exclude fees?

From CSV transactions:
```
2025-12-09,Buy,US64110L1061,Netflix,Stock,25,€82.93,€0.31,€-2,073.30
```
- Shares: 25
- Price: €82.93  
- Fees: €0.31
- Total: €-2,073.30

**Check:** 25 × €82.93 + €0.31 = €2,073.56 ≈ €2,073.30 ✓

So `total` INCLUDES fees, which is correct for cost basis.

### Issue 5: Split Adjustments
**CRITICAL:** Are splits applied BEFORE or AFTER cost basis calculation?

If splits adjust historical transactions retroactively, the moving average will be correct.
If splits are applied to current positions only, the cost basis will be WRONG.

**Need to check:** `services/corporate_actions.py`

---

## 🧪 Test Cases - Trace Through Real Data

### Test Case 1: Netflix (US64110L1061)

**Your Expected:** 25 shares @ €82.93 avg = €2,073.25 total cost

**Transaction History (from CSV):**
```
2025-12-09: BUY 25 @ €82.93, fees €0.31, total €-2,073.30
(No sells, no other transactions)
```

**Trace:**
```
Initial: shares=0, cost_basis=€0

BUY 25:
  amount_eur = -2073.30 × 1.0 = -2073.30
  amt = abs(-2073.30) = 2073.30
  cost_basis = 0 + 2073.30 = 2073.30
  shares = 0 + 25 = 25
  avg = 2073.30 / 25 = €82.93 ✓
```

**Expected Export:** 25 @ €82.93  
**Actual Export:** 25 @ €71.24  
**Discrepancy:** -€11.69

**🚨 PROBLEM FOUND!** Export shows €71.24 instead of €82.93.

**Possible causes:**
1. There ARE other Netflix transactions we haven't seen
2. Split adjustment is being applied incorrectly
3. There's a bug in the calculation

Let me search the full transaction export for ALL Netflix transactions...

### Test Case 2: Novo Nordisk (DK0062498333)

**Your Expected:** 50 shares @ €41.37 (DKK price)  
**Export Shows:** 50 shares @ €5.54

**Transaction History (sample from CSV):**
```
2025-12-10: BUY 50 @ €41.37, fees €1.37, total €-2,068.62, DKK, FX 0.1339
2025-12-08: SELL 64.24 @ €40.66, fees €1.00, total €2,611.79
... (many others)
```

**🚨 PROBLEM:** You bought 50 shares on 2025-12-10 but SOLD 64.24 on 2025-12-08 (BEFORE the buy!)

**This means there MUST be earlier BUY transactions we need to account for.**

---

## 🎯 DIAGNOSIS

The implementation is **THEORETICALLY CORRECT** but we need to:

1. ✅ **Verify transaction completeness** - Are we seeing ALL transactions?
2. ✅ **Check split adjustment timing** - Are splits being applied correctly?
3. ✅ **Trace through FULL history** - Not just recent transactions
4. ❌ **Fix TRANSFER_IN handling** - Currently doesn't preserve cost basis

---

## 🔧 Required Fixes

### Fix 1: TRANSFER_IN Cost Basis
```python
# Current (WRONG for zero-total transfers):
amt = abs(amount_eur)

# Should be:
if t.type == TransactionType.TRANSFER_IN:
    # If total is 0, use shares × price as cost basis
    if abs(amount_eur) < 0.01:  # Essentially zero
        amt = t.shares * t.price * t.fx_rate
    else:
        amt = abs(amount_eur)
else:
    amt = abs(amount_eur)
```

### Fix 2: Add Logging for Debugging
```python
# After each transaction, log the state
logger.debug(
    f"{t.date} {t.type.value} {t.ticker}: "
    f"{pos.shares:.4f} shares @ avg €{pos.cost_basis/pos.shares if pos.shares > 0 else 0:.2f}, "
    f"total cost €{pos.cost_basis:.2f}"
)
```

### Fix 3: Validate Against Expected
```python
# After reconstruction, compare to known good values
expected_positions = {
    'US64110L1061': {'shares': 25, 'avg_cost': 82.93},
    'DK0062498333': {'shares': 50, 'avg_cost': 41.37},
    # ... etc
}

for ticker, expected in expected_positions.items():
    if ticker in self.holdings:
        actual = self.holdings[ticker]
        actual_avg = actual.cost_basis / actual.shares
        if abs(actual.shares - expected['shares']) > 0.01:
            logger.error(f"{ticker}: Share mismatch! Expected {expected['shares']}, got {actual.shares}")
        if abs(actual_avg - expected['avg_cost']) > 1.0:
            logger.warning(f"{ticker}: Avg cost mismatch! Expected €{expected['avg_cost']}, got €{actual_avg:.2f}")
```

---

## 📋 Next Steps

1. **Search full transaction CSV** for ALL transactions of discrepant positions
2. **Trace through manually** to find where the calculation diverges
3. **Implement fixes** for TRANSFER_IN and add logging
4. **Re-run** and compare

**Ready to proceed with detailed trace-through of Netflix and Novo Nordisk?**
