# Deployment & Verification Guide

This guide outlines the procedures for verifying the installation integrity, validating the caching system, and hardening the application for production use.

## 1. Post-Installation Verification

After installing dependencies and launching the application (`streamlit run portfolio_viewer.py`), perform the following validation steps.

### A. Functional Integrity
1.  **Launch**: Ensure the web interface loads at `http://localhost:8501`.
2.  **Data Ingestion**: Upload a sample CSV file.
    *   *Success Criterion*: Dashboard renders without traceback errors.
    *   *Success Criterion*: "Net Worth" and "XIRR" metrics are calculated.
3.  **Market Data Access**: Check the sidebar for price fetching status.
    *   *Success Criterion*: Green "Fetched prices" message or specific warnings for delisted tickers.

### B. Caching System Validation
The application uses a persistent SQLite cache to optimize API precision.

**Verification Command:**
```bash
python view_cache_stats.py
```

**Expected Output:**
```text
Market Cache Statistics
=======================
Database Location: .../data/market_cache.db
Cache Statistics:
   • Total prices cached: [Integer > 0]
   • Unique tickers: [Integer > 0]
```

*Note: If `data/market_cache.db` is missing, the application has not successfully processed any transactions yet.*

### C. Observability Check
Verify that structured logging is active.

1.  Inspect the log directory: `logs/portfolio_viewer.log`
2.  Validate log rotation and formatting:
    ```bash
    # Linux/Mac
    tail -n 20 logs/portfolio_viewer.log
    ```
    *Look for lines containing `[INFO]`, `[market_cache]`, or `[csv_parser]`.*

## 2. Maintenance

### Log Rotation
Logs are automatically rotated at 10MB. To change this policy, modify `utils/logging_config.py`.

### Cache Reset
To force a complete refresh of market data (e.g., after corporate action corrections):
1.  Stop the application.
2.  Delete `data/market_cache.db`.
3.  Restart the application.
