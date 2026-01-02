# Quick Start Guide - Modular Monolith

## For End Users

### Option 1: Docker Compose (Recommended)
```bash
# Clone and run
git clone https://github.com/EGZX/PortfolioViewer.git
cd PortfolioViewer
docker-compose up -d

# Access at http://localhost:8501
```

### Option 2: Local Installation
```bash
# Clone repository
git clone https://github.com/EGZX/PortfolioViewer.git
cd PortfolioViewer

# Install dependencies
pip install -r requirements.txt

# Run application
streamlit run portfolio_viewer.py
```

## For Developers

### Using New Core Features

#### Database Access
```python
from core.db import get_db

# Get database instance
db = get_db()
db.init_schema()

# Query SQLite
trades = db.query_sqlite("SELECT * FROM trades WHERE date > ?", ("2024-01-01",))

# Analytical query with DuckDB (joins SQLite + Parquet)
result = db.query_duckdb("""
    SELECT t.ticker, AVG(p.close) as avg_price
    FROM sqlite_scan('portfolio.db', 'trades') t
    JOIN read_parquet('market_cache/*.parquet') p ON t.ticker = p.ticker
    GROUP BY t.ticker
""")
```

#### Market Data (Parquet)
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

# Load data
prices = market.load_price_data('AAPL', start_date='2024-01-01')
latest = market.get_latest_price('AAPL')
```

#### Audit Trails
```python
from core.hashing import create_audit_entry

# Create SHA256-sealed audit entry
entry = create_audit_entry(
    event_id="TAX_2024_001",
    inputs={"shares": 100, "cost_basis": 5000.0},
    outputs={"tax_due": 123.80}
)
# Entry includes calculation_hash for verification
```

#### Quant Analytics (NEW)
```python
from modules.quant.analytics import get_analyzer

analyzer = get_analyzer()

# Get all trades (read-only)
trades = analyzer.get_all_trades()

# Calculate return statistics
stats = analyzer.calculate_returns_distribution(ticker="AAPL")
print(f"Mean Return: {stats['mean_return']:.2%}")

# Concentration risk
risk = analyzer.get_concentration_risk()
print(f"Top 5 Concentration: {risk['top_5_concentration']:.2%}")

# Monte Carlo simulation
sim = analyzer.run_monte_carlo_simulation(num_simulations=1000)
print(f"Median outcome: {sim['percentile_50']:.2%}")
```

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run property-based tests
pytest tests/test_invariants.py -v

# Run specific test suite
pytest tests/test_austria_tax.py -v
```

### Project Structure

```
PortfolioViewer/
├── core/                   # The Kernel (data access)
│   ├── db.py              # Database manager
│   ├── market.py          # Parquet market data
│   └── hashing.py         # SHA256 audit logic
│
├── modules/               # Business logic
│   ├── tax/              # Tax engine
│   ├── viewer/           # Portfolio dashboard
│   └── quant/            # Analytics (read-only)
│
├── ui/                   # Streamlit frontend
├── tests/                # Tests (including property-based)
└── docs/
    ├── ARCHITECTURE.md   # Technical reference
    ├── MIGRATION.md      # Migration guide
    └── IMPLEMENTATION_SUMMARY.md
```

## Common Tasks

### Adding a New Tax Calculator
```python
# Create in modules/tax/calculators/my_country.py
from calculators.tax_calculators.base import BaseTaxCalculator

class MyCountryCalculator(BaseTaxCalculator):
    def calculate_tax_liability(self, events, tax_year):
        # Your logic here
        pass

# Register in modules/tax/calculators/__init__.py
```

### Adding New Analytics
```python
# Add to modules/quant/analytics.py
class ReadOnlyPortfolioAnalyzer:
    def my_new_analysis(self):
        trades = self.get_all_trades()
        # Your analysis logic (read-only!)
        return results
```

### Creating Property-Based Tests
```python
# Add to tests/test_invariants.py
from hypothesis import given, strategies as st

@given(price=st.decimals(min_value=0.01, max_value=10000))
def test_my_invariant(price):
    # Your invariant test
    assert price > 0
```

## Troubleshooting

**Issue**: DuckDB not available
```bash
pip install duckdb
```

**Issue**: Parquet support missing
```bash
pip install pyarrow
```

**Issue**: Tests failing with "No secrets found"
```bash
# Create .streamlit/secrets.toml with minimal config
mkdir -p .streamlit
cat > .streamlit/secrets.toml << EOF
[passwords]
app_password_hash = "test_hash"
EOF
```

**Issue**: Docker build failing (SSL certificates)
- This is a CI/CD environment issue
- Works correctly on local machines
- Use `docker-compose up -d` locally

## Documentation

- **ARCHITECTURE.md**: Complete technical reference (13.5KB)
- **MIGRATION.md**: Developer migration guide (10.8KB)
- **IMPLEMENTATION_SUMMARY.md**: Project completion summary (9.6KB)
- **README.md**: User-facing documentation

## Support

For issues or questions:
1. Check documentation (ARCHITECTURE.md, MIGRATION.md)
2. Review tests for usage examples
3. Open GitHub issue with `migration` or `architecture` label

## Next Steps

After getting started:
1. Read ARCHITECTURE.md for detailed design
2. Explore modules/quant/analytics.py for advanced features
3. Try property-based tests: `pytest tests/test_invariants.py -v`
4. Review MIGRATION.md if updating existing code

---

**Status**: ✅ Production Ready | **Version**: 1.0 (Modular Monolith)
