# Architecture Documentation

## Modular Monolith Platform - "Library-First" Design

### Vision
A "Library-First" Modular Monolith. The application runs as a single Docker container, but internally, code is strictly separated into **Data (The Kernel)**, **Logic (Modules)**, and **UI (Presentation)**.

---

## Directory Structure

```
/portfolio-platform
├── data/                   # [GIT IGNORED] Persistence Layer
│   ├── portfolio.db        # SQLite: Trades, Settings, Audit Logs
│   └── market_cache/       # Parquet: OHLCV Data (One file per ticker)
│
├── core/                   # The "Kernel"
│   ├── db.py               # DuckDB + SQLite connection manager
│   ├── market.py           # Data fetcher -> Parquet
│   └── hashing.py          # SHA256 audit logic
│
├── modules/
│   ├── tax/                # The Compliance Engine ("The Fortress")
│   │   ├── engine.py       # Tax calculation engine
│   │   └── calculators/    # Jurisdiction-specific calculators
│   ├── viewer/             # Dashboard Logic
│   │   ├── portfolio.py    # Portfolio state management
│   │   └── metrics.py      # Performance metrics (XIRR, Sharpe, etc.)
│   └── quant/              # Research Sandbox (Read-Only)
│       └── analytics.py    # Advanced analytics tools
│
├── ui/                     # Streamlit Frontend
├── tests/                  # Hypothesis & Invariant Tests
├── Dockerfile
└── docker-compose.yml
```

---

## Phase 1: The Data Kernel (DuckDB + SQLite)

### Objective
Establish the "Golden Copy" of data.

### Hybrid Storage Strategy

1. **Trades (SQLite)**: Stored in `data/portfolio.db`
   - Strict types
   - Foreign Keys
   - ACID compliance
   - Tables: `trades`, `settings`, `tax_audit_log`

2. **Prices (Parquet)**: Stored in `data/market_cache/`
   - Efficient columnar storage for time-series
   - One file per ticker (e.g., `AAPL.parquet`)
   - Columns: `date`, `open`, `high`, `low`, `close`, `volume`
   - Compressed with Snappy

3. **The Glue (DuckDB)**: Python wrapper to query both
   - Example: `duckdb.query("SELECT * FROM sqlite_scan('portfolio.db', 'trades')")`
   - Can join SQLite tables with Parquet files
   - In-memory analytical processing

### Core Components

#### `core/db.py` - Database Manager
```python
from core.db import get_db

db = get_db()

# Query SQLite
trades = db.query_sqlite("SELECT * FROM trades WHERE date > ?", ("2024-01-01",))

# Query with DuckDB (can access both SQLite and Parquet)
result = db.query_duckdb("""
    SELECT t.ticker, AVG(p.close) as avg_price
    FROM sqlite_scan('portfolio.db', 'trades') t
    JOIN read_parquet('market_cache/*.parquet') p 
      ON t.ticker = p.ticker
    GROUP BY t.ticker
""")
```

#### `core/hashing.py` - Audit Logic
Canonical JSON dumper + SHA256 hasher for audit trails.

```python
from core.hashing import create_audit_entry

audit_entry = create_audit_entry(
    event_id="TAX_2024_uuid",
    inputs={"shares": 100, "cost_basis": 5000.0},
    outputs={"tax_due": 123.80}
)
# Returns:
# {
#   "event_id": "TAX_2024_uuid",
#   "timestamp": "2024-03-15T10:30:00Z",
#   "calculation_hash": "sha256:...",
#   "inputs": {...},
#   "outputs": {...}
# }
```

#### `core/market.py` - Market Data Parquet
```python
from core.market import get_market_parquet
import pandas as pd

market = get_market_parquet()

# Save OHLCV data
data = pd.DataFrame({
    'date': [...],
    'open': [...],
    'high': [...],
    'low': [...],
    'close': [...],
    'volume': [...]
})
market.save_price_data('AAPL', data, append=True)

# Load data
prices = market.load_price_data('AAPL', start_date='2024-01-01')
latest = market.get_latest_price('AAPL')
```

---

## Phase 2: The Tax Engine ("The Fortress")

### Objective
Build an immutable, verifiable ledger.

### Logic

1. **Event Loop**: Replay history from chronological start
2. **Audit Record**: Append-only log in `portfolio.db` (`tax_audit_log` table)
3. **Sealed Calculations**: Each calculation is SHA256-sealed

### Audit Entry Structure
```python
audit_entry = {
    "event_id": "TAX_2024_uuid",
    "timestamp": "2024-03-15T10:30:00Z",
    "calculation_hash": "sha256:...",  # Input/Output Seal
    "inputs": {
        "shares": 100,
        "cost_basis": 5000.0,
        "sell_price": 5500.0
    },
    "outputs": {
        "realized_gain": 500.0,
        "tax_due": 123.80
    }
}
```

### Usage
```python
from modules.tax.engine import TaxBasisEngine
from modules.tax.calculators import get_calculator

# Process transactions
engine = TaxBasisEngine(transactions, matching_strategy="WeightedAverage")
engine.process_all_transactions()

# Get realized events
events = engine.get_realized_events(start_date, end_date)

# Calculate tax liability
calculator = get_calculator("AT")  # Austria
liability = calculator.calculate_tax_liability(events, tax_year=2024)
```

---

## Phase 3: The Quant Lab

### Objective
Powerful analysis, no architectural bloat.

### Read-Only Principle
Quant modules import `core.db` in **Read-Only mode**. Cannot alter trade history.

### Execution
Synchronous `ThreadPoolExecutor` for long tasks (>5s) to keep UI responsive. No Redis yet.

### Usage
```python
from modules.quant.analytics import get_analyzer

analyzer = get_analyzer()

# Get all trades (read-only)
trades = analyzer.get_all_trades()

# Calculate return distribution
stats = analyzer.calculate_returns_distribution(ticker="AAPL")
# Returns: mean_return, median_return, std_dev, skewness, kurtosis

# Holding period analysis
holding_periods = analyzer.get_holding_period_analysis()

# Concentration risk
risk = analyzer.get_concentration_risk()
# Returns: herfindahl_index, top_5_concentration, num_positions

# Monte Carlo simulation
simulation = analyzer.run_monte_carlo_simulation(
    num_simulations=1000,
    time_horizon_days=252
)
# Returns: percentile_5, percentile_50, percentile_95, mean_outcome
```

---

## Phase 4: Verification ("The Hypothesis")

### Objective
Mathematical correctness through property-based testing.

### Property-Based Testing
Uses `hypothesis` library for automated test generation.

### Invariants

1. **Non-Negative Cost Basis**
   ```python
   @given(shares=st.integers(min_value=1, max_value=1000),
          price=st.decimals(min_value=0.01, max_value=10000))
   def test_invariant_cost_basis_non_negative(shares, price):
       cost_basis = Decimal(shares) * price
       assert cost_basis >= 0
   ```

2. **Value Conservation**
   ```python
   # Realized + Unrealized = Total Value - Net Invested
   assert abs((realized + unrealized) - (total_value - net_invested)) < 0.01
   ```

3. **Portfolio Decomposition**
   ```python
   # Total Value = Sum(Holdings) + Cash
   assert abs(total_value - (holdings_sum + cash_balance)) < 0.02
   ```

### Running Tests
```bash
pytest tests/test_invariants.py -v
```

---

## Phase 5: Deployment

### Objective
Zero-config "Self-Sovereign" launch.

### Container
Single Docker container with all dependencies.

```bash
# Build
docker build -t portfolio-viewer .

# Run with docker-compose
docker-compose up -d

# Access at http://localhost:8501
```

### Network
- **Bind to**: `127.0.0.1:8501` (Host only)
- **Not exposed to internet** by default
- Use **Reverse Proxy** (nginx) or **Tailscale** for remote access

### Security
- Read-only root filesystem (except mounted volumes)
- Encrypted transaction storage (AES-256)
- SHA256 audit trails for tax calculations
- No external API keys required (optional for enhanced features)

### Docker Compose Configuration
```yaml
services:
  portfolio-platform:
    build: .
    ports:
      - "127.0.0.1:8501:8501"  # Localhost only
    volumes:
      - ./data:/app/data       # Persist data
    restart: unless-stopped
    read_only: true            # Security: read-only filesystem
    tmpfs:
      - /tmp
```

---

## Migration Path

### From Legacy Structure to Modular Monolith

**Current State** (Legacy):
```
calculators/
  ├── portfolio.py
  ├── metrics.py
  └── tax_basis.py
services/
  ├── market_data.py
  └── market_cache.py
```

**Target State** (Modular):
```
core/
  ├── db.py
  ├── market.py
  └── hashing.py
modules/
  ├── viewer/
  │   ├── portfolio.py    # symlink to calculators/portfolio.py
  │   └── metrics.py      # symlink to calculators/metrics.py
  ├── tax/
  │   └── engine.py       # symlink to calculators/tax_basis.py
  └── quant/
      └── analytics.py
```

**Migration Strategy**:
1. **Phase 1**: Create new structure with symlinks (backward compatible)
2. **Phase 2**: Gradually move imports to new paths
3. **Phase 3**: Remove legacy structure once all imports updated

---

## API Reference

### Core Kernel

#### DatabaseManager
```python
from core.db import get_db

db = get_db()
db.init_schema()                           # Initialize database schema
trades = db.query_sqlite(sql, params)      # Query SQLite
rows = db.query_duckdb(sql)                # Analytical queries
db.execute_sqlite(sql, params)             # Execute statement
path = db.get_parquet_path(ticker)         # Get parquet file path
db.close()                                 # Close connections
```

#### MarketDataParquet
```python
from core.market import get_market_parquet

market = get_market_parquet()
market.save_price_data(ticker, df, append=True)
df = market.load_price_data(ticker, start_date, end_date)
price = market.get_latest_price(ticker)
date_range = market.get_date_range(ticker)
exists = market.has_data(ticker)
```

#### Hashing & Audit
```python
from core.hashing import calculate_sha256, create_audit_entry, verify_hash

hash = calculate_sha256(data)
entry = create_audit_entry(event_id, inputs, outputs)
is_valid = verify_hash(data, expected_hash)
```

### Modules

#### Tax Engine
```python
from modules.tax.engine import TaxBasisEngine
from modules.tax.calculators import get_calculator

engine = TaxBasisEngine(transactions, matching_strategy="FIFO")
engine.process_all_transactions()
events = engine.get_realized_events(start_date, end_date)

calculator = get_calculator("AT")  # Austria
liability = calculator.calculate_tax_liability(events, tax_year)
```

#### Viewer
```python
from modules.viewer.portfolio import Portfolio
from modules.viewer.metrics import xirr, calculate_sharpe_ratio

portfolio = Portfolio(transactions)
total_value = portfolio.calculate_total_value(prices)
holdings = portfolio.get_holdings_summary(prices)

dates, amounts = portfolio.get_cash_flows_for_xirr(current_value)
xirr_value = xirr(dates, amounts)
```

#### Quant Analytics
```python
from modules.quant.analytics import get_analyzer

analyzer = get_analyzer()
trades = analyzer.get_all_trades()
stats = analyzer.calculate_returns_distribution(ticker="AAPL")
holding_periods = analyzer.get_holding_period_analysis()
risk = analyzer.get_concentration_risk()
simulation = analyzer.run_monte_carlo_simulation(num_simulations=1000)
```

---

## Performance Considerations

### Database Queries
- Use DuckDB for analytical queries (much faster than SQLite for aggregations)
- Parquet files enable columnar storage (efficient for time-series)
- Keep SQLite for transactional data (ACID compliance)

### Caching Strategy
- **L1 Cache**: In-memory (Python dictionaries)
- **L2 Cache**: Parquet files on disk
- **L3 Cache**: SQLite database

### Memory Management
- Parquet files are memory-mapped (low memory footprint)
- DuckDB uses lazy evaluation
- Portfolio state reconstruction is O(N) not O(N²)

---

## Security Model

### Data at Rest
- **Encryption**: AES-256 via Fernet for sensitive transaction data
- **Audit Trails**: SHA256 sealed calculations (tamper-evident)
- **Access Control**: File system permissions on `data/` directory

### Data in Transit
- **Local Only**: Default binding to 127.0.0.1
- **TLS**: Required for remote access (via reverse proxy)
- **Authentication**: PBKDF2 SHA-256 password hashing

### Threat Model
- **Trusted Environment**: Application runs in user-controlled environment
- **No External Exposure**: Not designed for public internet access
- **Self-Hosted**: User controls all infrastructure

---

## Future Enhancements

### Potential Extensions
1. **GraphQL API**: Expose data via GraphQL for advanced querying
2. **Real-time Streaming**: WebSocket updates for live prices
3. **Multi-User**: Add user management and permissions
4. **Backup/Sync**: Automated backup to encrypted cloud storage
5. **AI Insights**: ML-powered portfolio recommendations

### Architectural Evolution
- Current: **Modular Monolith** (single container)
- Future: **Microservices** (if needed for scale)
  - Tax Engine → Separate service
  - Market Data → Separate service
  - Quant Lab → Separate service

---

## Troubleshooting

### Common Issues

**Issue**: DuckDB import fails
```bash
pip install duckdb
```

**Issue**: Parquet support missing
```bash
pip install pyarrow
```

**Issue**: Tests failing with SSL errors (Docker build)
- This is a CI/CD infrastructure issue, not a code problem
- Locally, Docker builds should work fine

**Issue**: Property-based tests finding bugs
- This is expected! Hypothesis is uncovering edge cases
- Log them as issues and fix in future iterations

---

## Contributing

When contributing to this codebase:

1. **Respect Layer Boundaries**: Core → Modules → UI (one-way dependency)
2. **Read-Only Quant**: Never modify data in quant module
3. **Audit Everything**: Use `core.hashing` for verifiable calculations
4. **Test Properties**: Add hypothesis tests for new invariants
5. **Document Architecture**: Update this file for major changes

---

## License

Copyright (c) 2026 Andreas Wagner. All rights reserved.
