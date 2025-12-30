# Portfolio Viewer

A high-performance financial analytics dashboard built with Streamlit, designed for precision portfolio tracking, sophisticated performance metrics, and enterprise-grade data handling.

## 📋 Capabilities

### Core Features
- **Universal Import**: Smart parsing of CSV transaction logs with auto-detection for delimiters, locales (DE/EN), and column mappings.
- **Multi-Asset Support**: Native handling of Stocks, ETFs, Crypto, and Cash with automated asset type classification.
- **Foreign Exchange**: Automatic historical FX conversion (USD/EUR/DKK/etc.) for accurate base-currency valuation.

### Analytics & Visualization
- **XIRR Calculation**: Financial industry-standard Money-Weighted Return calculation using the Newton-Raphson method (via `scipy.optimize`).
- **Performance Attribution**: Interactive visualization of Net Deposits vs. Cost Basis vs. Market Value over configurable timeframes.
- **Holdings Analysis**: Drilling down into allocation, gains/losses, and tax-lot simulacra.

### Technical Architecture
- **Incremental Calculation Engine**: Implements an **O(N)** chronological state reconstruction algorithm for instantaneous historical charting, replacing legacy O(N²) methods.
- **Hybrid Caching**:
    - **Market Data**: Tiered SQLite caching strategy for high-frequency pricing data.
    - **Computation**: Memoized transaction processing for sub-second dashboard reloads.
- **Security**: SHA-256 hashed authentication and optional AES-256 encryption for cached market data at rest.

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- pip

### Installation

1.  **Clone and Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configuration (Optional)**
    Create `.streamlit/secrets.toml` to secure the instance:
    ```toml
    [passwords]
    # SHA-256 hash of your password
    app_password_hash = "e6c3da5b206634d7f3f3586d747ffdb36b5c675757b380c6a5fe5c570c714349" 
    
    # Optional: AES Key for cache encryption (generate via utils/auth.py)
    MARKET_CACHE_ENCRYPTION_KEY = "..." 
    ```

3.  **Execution**
    ```bash
    streamlit run portfolio_viewer.py
    ```

## 📂 Data Ingestion

The ingestion engine supports flexible CSV schemas. The parser uses fuzzy matching to identify columns.

**Required Columns:**
- `Date` (ISO 8601 or local format)
- `Type` (Buy, Sell, Dividend, TransferIn/Out, etc.)

**Recommended Columns:**
- `Ticker` / `ISIN`
- `Shares` / `Quantity`
- `Price` / `Amount`
- `Total` (Net flux)
- `Currency` (if non-EUR)

## 🏗️ System Architecture

```mermaid
graph TD
    User[User CSV] -->|Upload| Parser[CSV Parser]
    Parser -->|Normalize| Trans[Transaction Model]
    Trans -->|Process| Portfolio[Portfolio Engine]
    
    subgraph "Data Layer"
        YF[yfinance API] -->|Fetch| Cache[(SQLite Cache)]
        Cache -->|Serve| Service[Market Data Service]
    end
    
    Service -->|Prices| Portfolio
    Portfolio -->|Metrics| UI[Streamlit Dashboard]
```

### Logging & Observability

The application maintains structured, rotating logs in `logs/portfolio_viewer.log` for debugging and audit trails.

- **Rotation**: 10MB limit, 5 backups.
- **Format**: `[TIMESTAMP] [LEVEL] [MODULE] Message`
- **Performance Tracing**: Operations exceeding 1000ms are flagged with `SLOW` log entries for bottleneck identification.

## 🛠️ Development

### Testing
```bash
# Verify integrity of tax logic and calculations
python -m unittest discover tests
```

### Password Hashing Utility
```bash
# Generate hash for secrets.toml
python -c "from utils.auth import generate_password_hash; print(generate_password_hash('your_password'))"
```

## License

MIT License. See `LICENSE` for details.
