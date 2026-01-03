# Critical Bug Fixes - Realized P/L and Asset Tracking

## Date: 2026-01-02

## Issues Addressed

### 1. **Realized P/L Incorrectly Calculated (€68,240 vs €5,628.92 expected)**
   - **Root Cause**: ISIN/Ticker identifier mismatch between Portfolio and Tax Engine.
   - **Resolution**: Both engines now prioritize **ISIN** for persistent tracking, while using Ticker only for pricing.

### 2. **Asset Allocation Showing ISINs Instead of Tickers**
   - **Root Cause**: ISINs were bleeding into the `ticker` field during CSV import.
   - **Resolution**: Fixed CSV parser to keep ISIN and Ticker separate. Portfolio now maps ISIN-keyed holdings to Tickers for display.

### 3. **Performance History Chart Not Loading**
   - **Resolution**: Added auto-trigger for historical data fetch on first load.

## Technical Architecture Changes

### ✅ Corrected Asset Tracking Strategy
We successfully refactored the application to use the correct data types for their intended purposes:

1. **Tax & Position Tracking**: Uses **ISIN** (if available)
   - Stable, globally unique, never changes.
   - Perfect for matching buy/sell lots over years.
   - **Constraint**: Tax Engine and Portfolio now both prefer ISIN keying.

2. **Market Data & Display**: Uses **Ticker**
   - Required for API lookups (Yahoo Finance).
   - Can change (stock splits, symbol changes), so not used for primary key.
   - Portfolio maps `ISIN -> Ticker` for pricing calls.

### Implemented Fixes

#### 1. CSV Parser (`lib/parsers/csv_parser.py`)
- **Fix**: Stopped copying ISIN into the `ticker` field when ticker is missing.
- **Effect**: Ticker field stays empty if not provided, allowing strict separation.

#### 2. Portfolio (`modules/viewer/portfolio.py`)
- **Internal Key**: Now uses `ISIN` as the primary key for the `holdings` dictionary.
- **Pricing & Display**: Methods `calculate_total_value` and `get_holdings_summary` now look up the **Ticker** from the stored Position object, ignoring the ISIN key.
- **Result**: Robust internal tracking + Beautiful external display (Tickers).

#### 3. Tax Engine (`modules/tax/engine.py`)
- **Restored**: Reverted to **ISIN-first** key generation.
- **Reason**: Matches the Portfolio's new ISIN-first tracking logic.

#### 4. Pipeline (`lib/pipeline.py`)
- **Enrichment**: Resolves ISINs to Tickers using OpenFIGI/Overrides but **stores the ticker in the ticker field** without overwriting the ISIN.

## Expected Outcomes

### Realized P/L
**Before**: ~€68k (Duplicate events due to key mismatch)
**After**: ~€5,629 (Correctly matched lots)

### Display
**Charts**: Show Tickers (e.g., `SHOP`, `MSFT`)
**Allocation**: Uses correct Symbols.

### Warnings
**"Selling more than owned"**: Eliminated (Portfolio now correctly identifies asset by ISIN).

## Deployment Steps
1. **Clear Cache**: Required to flush old "ISIN-in-Ticker-field" transactions.
2. **Reload**: App will re-parse CSVs with strict separation.
3. **Verify**: Check KPIs against broker statement.
