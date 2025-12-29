# Portfolio Viewer

A production-grade portfolio analysis tool built with Streamlit that ingests CSV transactions, fetches live market data, and calculates sophisticated performance metrics including XIRR.

## Features

- ✅ **CSV Import**: Auto-detects German/English CSV formats (semicolon/comma delimiters)
- ✅ **Multi-Currency**: Handles USD, EUR, DKK with automatic FX conversion
- ✅ **Live Market Data**: Fetches current prices from yfinance with caching
- ✅ **XIRR Calculation**: Scientifically rigorous using Newton-Raphson method
- ✅ **Interactive Charts**: Plotly visualizations (allocation donut, performance area chart)
- ✅ **Password Protection**: Secure authentication using Streamlit secrets
- ✅ **Type-Safe**: Pydantic validation throughout
- ✅ **High Performance**: SQLite cache for market data (10-50x faster on subsequent loads)
- ✅ **Enhanced Logging**: Detailed logs with error categorization for easy debugging

> 📖 **New**: See [PERFORMANCE_AND_LOGGING.md](PERFORMANCE_AND_LOGGING.md) for details on performance improvements and logging features.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Password (Optional but Recommended)

Generate a password hash:
```bash
python -c "from utils.auth import generate_password_hash; print(generate_password_hash('YourPasswordHere'))"
```

Create `.streamlit/secrets.toml`:
```toml
[passwords]
app_password_hash = "YOUR_GENERATED_HASH_HERE"
```

**Example** (password: "admin123"):
```toml
[passwords]
app_password_hash = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
```

> **Note**: If no password is configured, the app will run without authentication (with a warning).

### 3. Run the Application
```bash
streamlit run portfolio_viewer.py
```

The app will open in your browser at `http://localhost:8501`

### 4. Upload Your CSV

1. Click "Upload Transaction CSV" in the sidebar
2. Select your transaction history CSV file
3. View your portfolio metrics and visualizations


## CSV Format

### Supported Columns

| Column | Aliases | Required | Description |
|--------|---------|----------|-------------|
| Date | datetime, datum, time | ✅ | Transaction date |
| Type | typ, transaction_type, action | ✅ | Buy, Sell, Dividend, TransferIn/Out, Interest |
| Ticker | symbol, isin, identifier, wkn, holding | ⚪ | Security identifier |
| Shares | amount, quantity, units | ⚪ | Number of shares |
| Price | unit_price, share_price | ⚪ | Price per share |
| Fees | fee, commission, cost | ⚪ | Transaction fees |
| Total | net_amount, cash_flow | ⚪ | Net cash flow (auto-calculated if missing) |
| Currency | originalcurrency | ⚪ | Transaction currency (default: EUR) |
| FXRate | exchange_rate, fx, rate | ⚪ | Exchange rate to EUR |

### Format Auto-Detection

The parser automatically detects:
- **Delimiter**: Semicolon (`;`) or comma (`,`)
- **Decimal separator**: Comma (`,`) or period (`.`)
- **Quote character**: Double quotes (`"`)
- **Column names**: Fuzzy matching (case-insensitive)

### Example CSV (German Format)
```csv
"datetime";"type";"ticker";"shares";"price";"fees";"total";"currency";"fxrate"
"2025-01-15T10:30:00";"Buy";"US0378331005";10;150,50;1,00;-1506,00;"USD";1,05
"2025-02-20T14:15:00";"Sell";"US0378331005";5;155,25;0,50;776,75;"USD";1,05
"2025-03-01T09:00:00";"Dividend";"US0378331005";5;0,50;0,00;2,50;"USD";1,05
```

## Architecture

```
PortfolioViewer/
├── portfolio_viewer.py         # Main Streamlit app
├── requirements.txt            # Dependencies
├── generate_cache_key.py       # NEW: Encryption key generator
├── PERFORMANCE_AND_LOGGING.md  # NEW: Performance & logging docs
├── data/                       # NEW: Cache database (git ignored)
│   └── market_cache.db
├── logs/                       # NEW: Log files (git ignored)
│   └── portfolio_viewer.log
├── parsers/
│   └── csv_parser.py          # CSV ingestion with auto-detection
├── calculators/
│   ├── portfolio.py           # Portfolio state manager
│   └── metrics.py             # XIRR & performance calculations
├── services/
│   ├── market_cache.py        # NEW: SQLite cache for prices/splits
│   ├── market_data.py         # yfinance integration (cached)
│   └── corporate_actions.py   # Stock splits with caching
├── charts/
│   └── visualizations.py      # Plotly charts
└── utils/
    ├── auth.py                # Password authentication
    └── logging_config.py      # Structured file logging
```

## Security

### Password Protection

The app uses **SHA-256 hashing** for password storage. Passwords are:
- ✅ Never stored in plain text
- ✅ Hashed using cryptographic algorithm (SHA-256)
- ✅ Stored in `.streamlit/secrets.toml` (excluded from git)
- ✅ Session-based authentication (logout available)

### Market Data Encryption (Optional)

The market data cache can be encrypted for added security:
- ✅ AES-based encryption (Fernet)
- ✅ Encrypted at rest in SQLite database
- ✅ Encryption key stored in `.streamlit/secrets.toml`
- ✅ Recommended for public repositories

**Setup**:
```bash
# Generate encryption key
python generate_cache_key.py

# Add to .streamlit/secrets.toml
# MARKET_CACHE_ENCRYPTION_KEY = "generated-key-here"
```

### Best Practices

1. **Never commit** `.streamlit/secrets.toml` to version control
2. Use a **strong password** (12+ characters, mixed case, numbers, symbols)
3. **Rotate passwords** regularly
4. Deploy on private networks or use HTTPS in production
5. Enable cache encryption if repository is public

## Performance Metrics

### Net Worth
Current portfolio value (holdings at market price + cash balance)

### Total Invested
Sum of all deposits and buy transactions

### Absolute Gain
```
Gain = (Current Value + Withdrawn) - Invested
```

### XIRR (Extended Internal Rate of Return)
Annualized money-weighted return that accounts for the timing of cash flows.

**Formula**: Solves for `r` where NPV = 0
```
NPV = Σ(CF_i / (1 + r)^(days_i / 365)) = 0
```

## Troubleshooting

### "No valid transactions found in CSV"

**Possible causes**:
1. CSV delimiter not detected correctly
2. Required columns ('date', 'type') missing or misspelled
3. Date format not recognized

**Solutions**:
- Ensure CSV has `date` and `type` columns
- Check delimiter (should be `;` or `,`)
- Verify dates are in format: `YYYY-MM-DD` or `DD.MM.YYYY`
- Check console logs for detailed error messages

### Password not working

**Solutions**:
1. Verify hash was generated correctly
2. Check `.streamlit/secrets.toml` file exists and has correct format
3. Restart Streamlit app after changing secrets
4. Ensure no extra spaces in hash string

### Market data fetch failures

**Solutions**:
- Check internet connection
- Verify ticker symbols are Yahoo Finance compatible
- App will fallback to last transaction price automatically
- Check sidebar for specific failed tickers

## Development

### Generate Password Hash
```bash
python utils/auth.py "your_password"
```

### Run Tests
```bash
# Upload test CSV and verify:
# 1. Transactions parsed correctly
# 2. Market data fetched
# 3. XIRR calculated
# 4. Charts rendered
```

### Logging
Logs are written to stdout. Check console for debugging:
```bash
streamlit run portfolio_viewer.py 2>&1 | tee app.log
```

## Dependencies

- **streamlit** ≥1.28.0 - Web UI framework
- **pandas** ≥2.0.0 - Data manipulation
- **numpy** ≥1.24.0 - Numerical computing
- **scipy** ≥1.11.0 - Scientific computing (XIRR)
- **yfinance** ≥0.2.28 - Market data API
- **plotly** ≥5.17.0 - Interactive charts
- **pydantic** ≥2.0.0 - Data validation

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review console logs for error messages
3. Ensure CSV format matches specifications

---

**Built with ❤️ using Streamlit, Pandas, and modern Python**
