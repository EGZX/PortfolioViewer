# Migration Guide: Legacy to Modular Monolith

This guide helps developers migrate code from the legacy structure to the new modular monolith architecture.

## Overview

The refactoring introduces a clear separation of concerns:
- **Core**: Data access and foundational utilities
- **Modules**: Business logic organized by domain
- **UI**: Presentation layer

## Quick Reference

### Import Changes

| Legacy Import | New Import | Status |
|--------------|------------|--------|
| `from calculators.portfolio import Portfolio` | `from modules.viewer.portfolio import Portfolio` | ✅ Backward compatible (symlink) |
| `from calculators.metrics import xirr` | `from modules.viewer.metrics import xirr` | ✅ Backward compatible (symlink) |
| `from calculators.tax_basis import TaxBasisEngine` | `from modules.tax.engine import TaxBasisEngine` | ✅ Backward compatible (symlink) |
| `from calculators.tax_calculators import get_calculator` | `from modules.tax.calculators import get_calculator` | ✅ Backward compatible (symlink) |
| N/A | `from core.db import get_db` | ⚡ New functionality |
| N/A | `from core.market import get_market_parquet` | ⚡ New functionality |
| N/A | `from core.hashing import create_audit_entry` | ⚡ New functionality |
| N/A | `from modules.quant.analytics import get_analyzer` | ⚡ New functionality |

## Phase 1: Using New Core Features

### Database Access (Hybrid Storage)

**Before**: Direct SQLite access scattered across codebase
```python
import sqlite3
conn = sqlite3.connect('data/market_cache.db')
cursor = conn.execute("SELECT * FROM trades")
```

**After**: Unified database manager
```python
from core.db import get_db

db = get_db()
trades = db.query_sqlite("SELECT * FROM trades WHERE date > ?", ("2024-01-01",))
```

**With DuckDB** (analytical queries):
```python
from core.db import get_db

db = get_db()

# Query both SQLite and Parquet files
result = db.query_duckdb("""
    SELECT t.ticker, COUNT(*) as num_trades, AVG(p.close) as avg_price
    FROM sqlite_scan('portfolio.db', 'trades') t
    LEFT JOIN read_parquet('market_cache/*.parquet') p 
        ON t.ticker = p.ticker
    GROUP BY t.ticker
""")
```

### Market Data Storage

**Before**: SQLite-based market cache
```python
from services.market_cache import get_market_cache
cache = get_market_cache()
prices = cache.get_prices_batch(tickers)
```

**After**: Parquet-based market storage (more efficient)
```python
from core.market import get_market_parquet
import pandas as pd

market = get_market_parquet()

# Save OHLCV data
data = pd.DataFrame({
    'date': pd.date_range('2024-01-01', periods=10),
    'open': [...], 'high': [...], 'low': [...], 
    'close': [...], 'volume': [...]
})
market.save_price_data('AAPL', data, append=True)

# Load historical data
prices = market.load_price_data('AAPL', start_date='2024-01-01')

# Get latest price
latest = market.get_latest_price('AAPL')
```

### Audit Trails (Tax Calculations)

**New**: Add SHA256-sealed audit entries
```python
from core.hashing import create_audit_entry
from core.db import get_db

# Create sealed audit entry
entry = create_audit_entry(
    event_id=f"TAX_{year}_{uuid4()}",
    inputs={
        "shares": 100,
        "cost_basis": 5000.0,
        "sell_price": 5500.0
    },
    outputs={
        "realized_gain": 500.0,
        "tax_due": 123.80
    }
)

# Store in database
db = get_db()
db.execute_sqlite("""
    INSERT INTO tax_audit_log (event_id, timestamp, calculation_hash, inputs, outputs)
    VALUES (?, ?, ?, ?, ?)
""", (
    entry['event_id'],
    entry['timestamp'],
    entry['calculation_hash'],
    json.dumps(entry['inputs']),
    json.dumps(entry['outputs'])
))
```

## Phase 2: Using New Module Structure

### Tax Module

**Legacy Path**: `calculators/tax_basis.py`
**New Path**: `modules/tax/engine.py` (currently symlinked)

**Usage remains the same** (backward compatible):
```python
# Old import still works
from calculators.tax_basis import TaxBasisEngine

# New import (recommended)
from modules.tax.engine import TaxBasisEngine

# Usage unchanged
engine = TaxBasisEngine(transactions, matching_strategy="FIFO")
engine.process_all_transactions()
events = engine.get_realized_events(start_date, end_date)
```

### Viewer Module

**Legacy Path**: `calculators/portfolio.py`, `calculators/metrics.py`
**New Path**: `modules/viewer/` (currently symlinked)

**Usage remains the same** (backward compatible):
```python
# Old imports still work
from calculators.portfolio import Portfolio
from calculators.metrics import xirr, calculate_sharpe_ratio

# New imports (recommended)
from modules.viewer.portfolio import Portfolio
from modules.viewer.metrics import xirr, calculate_sharpe_ratio

# Usage unchanged
portfolio = Portfolio(transactions)
total_value = portfolio.calculate_total_value(prices)
```

### Quant Module (NEW)

**New Path**: `modules/quant/analytics.py`

**Usage**:
```python
from modules.quant.analytics import get_analyzer

# Get read-only analyzer
analyzer = get_analyzer()

# Access all trades (read-only)
trades_df = analyzer.get_all_trades()

# Calculate statistical measures
stats = analyzer.calculate_returns_distribution(
    ticker="AAPL",
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31)
)
print(f"Mean Return: {stats['mean_return']:.2%}")
print(f"Volatility: {stats['std_dev']:.2%}")
print(f"Skewness: {stats['skewness']:.2f}")

# Holding period analysis
periods = analyzer.get_holding_period_analysis()

# Portfolio concentration risk
risk = analyzer.get_concentration_risk()
print(f"Herfindahl Index: {risk['herfindahl_index']:.4f}")
print(f"Top 5 Concentration: {risk['top_5_concentration']:.2%}")

# Monte Carlo simulation
simulation = analyzer.run_monte_carlo_simulation(
    num_simulations=10000,
    time_horizon_days=252,  # 1 year
    seed=42
)
print(f"5th percentile outcome: {simulation['percentile_5']:.2%}")
print(f"Median outcome: {simulation['percentile_50']:.2%}")
print(f"95th percentile outcome: {simulation['percentile_95']:.2%}")
```

## Phase 3: Testing

### Property-Based Tests (NEW)

**File**: `tests/test_invariants.py`

**Running tests**:
```bash
# Run all tests
pytest tests/ -v

# Run only property-based tests
pytest tests/test_invariants.py -v

# Run specific test
pytest tests/test_invariants.py::test_invariant_cost_basis_non_negative -v

# Run with hypothesis verbosity
pytest tests/test_invariants.py -v --hypothesis-verbosity=verbose
```

**Adding new property-based tests**:
```python
from hypothesis import given, strategies as st
from decimal import Decimal

@given(
    shares=st.integers(min_value=1, max_value=1000),
    price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), places=2)
)
def test_my_invariant(shares, price):
    # Your test logic here
    cost = Decimal(shares) * price
    assert cost >= 0
```

## Phase 4: Deployment

### Docker Compose (NEW)

**Before**: Manual Docker commands
```bash
docker build -t portfolio-viewer .
docker run -d -p 8501:8501 portfolio-viewer
```

**After**: Docker Compose
```bash
# Start
docker-compose up -d

# Stop
docker-compose down

# View logs
docker-compose logs -f

# Rebuild
docker-compose up -d --build
```

**Configuration**: `docker-compose.yml`
- Binds to `127.0.0.1:8501` for security
- Persists data in `./data` volume
- Read-only root filesystem
- Health checks enabled

## Phase 5: Configuration Changes

### Requirements

**New dependencies** added to `requirements.txt`:
```txt
duckdb>=0.9.0       # For analytical queries
pyarrow>=14.0.0     # For Parquet support
hypothesis>=6.92.0  # For property-based testing
pytest>=7.4.0       # For testing
```

**Install**:
```bash
pip install -r requirements.txt
```

### .gitignore

**New exclusion**:
```
# Data directory (Git ignored - persistence layer)
data/
```

**Rationale**: The `data/` directory contains user's financial data and should not be committed.

## Migration Checklist

### For Existing Codebases

- [ ] Install new dependencies: `pip install -r requirements.txt`
- [ ] Test backward compatibility: `pytest tests/`
- [ ] Update imports gradually (optional, symlinks maintain compatibility)
- [ ] Add property-based tests for critical invariants
- [ ] Update Docker deployment to use `docker-compose.yml`
- [ ] Verify `data/` directory is git-ignored

### For New Features

- [ ] Use `core.db` for database access (not direct SQLite)
- [ ] Use `core.market` for market data (not SQLite cache)
- [ ] Add audit trails with `core.hashing` for verifiable calculations
- [ ] Place business logic in appropriate module (`tax`, `viewer`, `quant`)
- [ ] Add property-based tests for mathematical invariants
- [ ] Document in `ARCHITECTURE.md`

## Common Issues

### Import Errors

**Issue**: `ModuleNotFoundError: No module named 'core'`

**Solution**: Ensure you're running from the project root:
```bash
cd /path/to/PortfolioViewer
python -m pytest tests/
```

### DuckDB Not Available

**Issue**: `RuntimeError: DuckDB not installed`

**Solution**: Install DuckDB:
```bash
pip install duckdb
```

### Parquet Support Missing

**Issue**: `Parquet support not available`

**Solution**: Install PyArrow:
```bash
pip install pyarrow
```

### Symlinks Not Working (Windows)

**Issue**: Symlinks may not work on Windows without admin rights

**Solution**: Copy files instead of symlinking:
```bash
# modules/viewer/
cp calculators/portfolio.py modules/viewer/portfolio.py
cp calculators/metrics.py modules/viewer/metrics.py

# modules/tax/
cp calculators/tax_basis.py modules/tax/engine.py
cp -r calculators/tax_calculators modules/tax/calculators
```

## Rollback Plan

If you encounter issues with the new structure:

1. **Remove symlinks**:
```bash
rm modules/viewer/portfolio.py modules/viewer/metrics.py
rm modules/tax/engine.py modules/tax/calculators
```

2. **Revert imports** to legacy paths:
```python
# Use legacy imports
from calculators.portfolio import Portfolio
from calculators.metrics import xirr
from calculators.tax_basis import TaxBasisEngine
```

3. **Keep using existing services**:
```python
from services.market_cache import get_market_cache
from services.market_data import fetch_prices
```

The legacy structure is still fully functional. The new structure is additive and non-breaking.

## Questions?

For questions about the migration:
1. Review `ARCHITECTURE.md` for detailed design documentation
2. Check existing tests for usage examples
3. Open an issue on GitHub with the `migration` label

## Timeline

- **Phase 1** (Current): Core kernel and modules created, symlinks for backward compatibility
- **Phase 2** (Next): Gradual import migration across codebase
- **Phase 3** (Future): Remove symlinks, full migration complete
- **Phase 4** (Future): Potential microservices split if needed

**No breaking changes** are planned for Phase 1 or 2. All migrations are backward compatible.
