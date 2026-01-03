"""
Market Data Access Layer

Provides clean interface to the market data tables in core database.
Replaces old MarketDataCache with new architecture.
"""

from datetime import date
from typing import Optional, List, Dict, Tuple
import pandas as pd
from core.db import get_db
from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


def get_price(ticker: str, target_date: date) -> Optional[float]:
    """Get price for ticker on specific date."""
    db = get_db()
    rows = db.query_sqlite(
        "SELECT price FROM prices WHERE ticker = ? AND date = ?",
        (ticker, target_date)
    )
    return rows[0]['price'] if rows else None


def set_price(ticker: str, price: float, price_date: date, source: str = 'yfinance'):
    """Store price in database."""
    db = get_db()
    db.execute_sqlite(
        "INSERT OR REPLACE INTO prices (ticker, date, price, source) VALUES (?, ?, ?, ?)",
        (ticker, price_date, price, source)
    )


def get_prices_batch(tickers: List[str], target_date: date) -> Dict[str, Optional[float]]:
    """Get prices for multiple tickers on a single date."""
    if not tickers:
        return {}
    
    db = get_db()
    placeholders = ','.join('?' * len(tickers))
    rows = db.query_sqlite(
        f"SELECT ticker, price FROM prices WHERE ticker IN ({placeholders}) AND date = ?",
        (*tickers, target_date)
    )
    
    result = {t: None for t in tickers}
    for row in rows:
        result[row['ticker']] = row['price']
    
    return result


def set_prices_batch(prices: List[Tuple[str, date, float, str]]):
    """Bulk insert prices. Format: [(ticker, date, price, source), ...]"""
    if not prices:
        return
    
    db = get_db()
    for ticker, price_date, price, source in prices:
        db.execute_sqlite(
            "INSERT OR REPLACE INTO prices (ticker, date, price, source) VALUES (?, ?, ?, ?)",
            (ticker, price_date, price, source)
        )


def get_historical_prices(tickers: List[str], start_date: date, end_date: date) -> pd.DataFrame:
    """Get historical prices as DataFrame."""
    if not tickers:
        return pd.DataFrame()
    
    db = get_db()
    placeholders = ','.join('?' * len(tickers))
    rows = db.query_sqlite(
        f"""SELECT ticker, date, price 
            FROM prices 
            WHERE ticker IN ({placeholders}) 
              AND date BETWEEN ? AND ?
            ORDER BY date""",
        (*tickers, start_date, end_date)
    )
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    pivot = df.pivot(index='date', columns='ticker', values='price')
    return pivot


def get_fx_rate(from_curr: str, to_curr: str, target_date: date) -> Optional[float]:
    """Get FX rate for currency pair on specific date."""
    db = get_db()
    rows = db.query_sqlite(
        "SELECT rate FROM fx_rates WHERE from_curr = ? AND to_curr = ? AND date = ?",
        (from_curr, to_curr, target_date)
    )
    return rows[0]['rate'] if rows else None


def set_fx_rate(from_curr: str, to_curr: str, target_date: date, rate: float):
    """Store FX rate."""
    db = get_db()
    db.execute_sqlite(
        "INSERT OR REPLACE INTO fx_rates (from_curr, to_curr, date, rate) VALUES (?, ?, ?, ?)",
        (from_curr, to_curr, target_date, rate)
    )


def get_split(ticker: str, split_date: date) -> Optional[float]:
    """Get split ratio for ticker on specific date."""
    db = get_db()
    rows = db.query_sqlite(
        "SELECT ratio FROM splits WHERE ticker = ? AND split_date = ?",
        (ticker, split_date)
    )
    return rows[0]['ratio'] if rows else None


def set_split(ticker: str, split_date: date, ratio: float):
    """Store split ratio."""
    db = get_db()
    db.execute_sqlite(
        "INSERT OR REPLACE INTO splits (ticker, split_date, ratio) VALUES (?, ?, ?)",
        (ticker, split_date, ratio)
    )


def resolve_isin(isin: str) -> Optional[str]:
    """Get ticker for ISIN."""
    db = get_db()
    rows = db.query_sqlite(
        "SELECT ticker FROM isin_map WHERE isin = ?",
        (isin,)
    )
    return rows[0]['ticker'] if rows else None


def store_isin_mapping(isin: str, ticker: str, name: str = None, exchange: str = None):
    """Store ISIN to ticker mapping."""
    db = get_db()
    db.execute_sqlite(
        "INSERT OR REPLACE INTO isin_map (isin, ticker, name, exchange) VALUES (?, ?, ?, ?)",
        (isin, ticker, name, exchange)
    )

def create_currency_table():
    """Initialize currency table."""
    db = get_db()
    db.execute_sqlite("""
        CREATE TABLE IF NOT EXISTS ticker_currencies (
            ticker TEXT PRIMARY KEY,
            currency TEXT
        )
    """)

def get_ticker_currency(ticker: str) -> Optional[str]:
    """Get cached trading currency for ticker."""
    db = get_db()
    try:
        rows = db.query_sqlite("SELECT currency FROM ticker_currencies WHERE ticker = ?", (ticker,))
        return rows[0]['currency'] if rows else None
    except Exception:
        return None

def set_ticker_currency(ticker: str, currency: str):
    """Cache trading currency for ticker."""
    if not currency:
        return
    db = get_db()
    try:
        db.execute_sqlite(
            "INSERT OR REPLACE INTO ticker_currencies (ticker, currency) VALUES (?, ?)",
            (ticker, currency)
        )
    except Exception:
        create_currency_table()
        db.execute_sqlite(
            "INSERT OR REPLACE INTO ticker_currencies (ticker, currency) VALUES (?, ?)",
            (ticker, currency)
        )

def create_blacklist_table():
    """Initialize blacklist table."""
    db = get_db()
    db.execute_sqlite("""
        CREATE TABLE IF NOT EXISTS ticker_blacklist (
            ticker TEXT PRIMARY KEY,
            ignored_since DATE
        )
    """)

def is_blacklisted(ticker: str) -> bool:
    """Check if ticker is blacklisted."""
    db = get_db()
    try:
        rows = db.query_sqlite("SELECT 1 FROM ticker_blacklist WHERE ticker = ?", (ticker,))
        return bool(rows)
    except Exception:
        return False

def set_blacklisted_ticker(ticker: str):
    """Add ticker to blacklist."""
    db = get_db()
    try:
        db.execute_sqlite(
            "INSERT OR REPLACE INTO ticker_blacklist (ticker, ignored_since) VALUES (?, ?)",
            (ticker, date.today())
        )
    except Exception:
        create_blacklist_table()
        db.execute_sqlite(
            "INSERT OR REPLACE INTO ticker_blacklist (ticker, ignored_since) VALUES (?, ?)",
            (ticker, date.today())
        )


# Legacy compatibility class (for gradual migration)
class MarketDataCache:
    """
    Lightweight wrapper providing old API interface.
    Delegates to new core database functions.
    """
    
    def get_price(self, ticker: str, target_date: date) -> Optional[float]:
        return get_price(ticker, target_date)
    
    def set_price(self, ticker: str, price: float, price_date: date, source: str = 'yfinance'):
        return set_price(ticker, price, price_date, source)
    
    def get_prices_batch(self, tickers: List[str], target_date: date = None) -> Dict[str, Optional[float]]:
        """Get batch of prices. If target_date is None, gets latest available."""
        if target_date is None:
            # Get latest price for each ticker (most recent date)
            db = get_db()
            result = {}
            for ticker in tickers:
                rows = db.query_sqlite(
                    "SELECT price FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
                    (ticker,)
                )
                result[ticker] = rows[0]['price'] if rows else None
            return result
        else:
            return get_prices_batch(tickers, target_date)
    
    def set_prices_batch(self, prices: List[Tuple[str, date, float, str]]):
        return set_prices_batch(prices)
    
    def get_historical_prices(self, tickers: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        return get_historical_prices(tickers, start_date, end_date)
    
    def get_fx_rate(self, from_curr: str, to_curr: str,  target_date: date) -> Optional[float]:
        return get_fx_rate(from_curr, to_curr, target_date)
    
    def set_fx_rate(self, from_curr: str, to_curr: str, target_date: date, rate: float):
        return set_fx_rate(from_curr, to_curr, target_date, rate)
    
    def get_isin_mapping(self, isin: str) -> Optional[str]:
        """Get ticker for ISIN (for cache detection logic)."""
        return resolve_isin(isin)
    
    def set_isin_mapping(self, isin: str, ticker: str, name: str = None, exchange: str = None):
        """Store ISIN to ticker mapping."""
        return store_isin_mapping(isin, ticker, name, exchange)
    
    def save_isin_mapping(self, isin: str, ticker: str, name: str = None, exchange: str = None):
        """Alias for set_isin_mapping (backward compatibility)."""
        return store_isin_mapping(isin, ticker, name, exchange)
    
    def get_ticker_currency(self, ticker: str) -> Optional[str]:
        return get_ticker_currency(ticker)
    
    def set_ticker_currency(self, ticker: str, currency: str):
        return set_ticker_currency(ticker, currency)

    def is_blacklisted(self, ticker: str) -> bool:
        return is_blacklisted(ticker)
        
    def blacklist_ticker(self, ticker: str):
        set_blacklisted_ticker(ticker)
    
    def get_last_transactions_csv(self) -> Optional[Tuple[str, str, date]]:
        """
        Legacy method for single-file mode cache.
        Returns None - single-file mode deprecated, use TransactionStore instead.
        """
        logger.warning("get_last_transactions_csv called - deprecated, use TransactionStore")
        return None
    
    def save_transactions_csv(self, content: str, filename: str):
        """
        Legacy method for single-file mode cache.
        Does nothing - single-file mode deprecated, use TransactionStore instead.
        """
        logger.warning("save_transactions_csv called - deprecated, use TransactionStore")
        pass
    
    def get_splits(self, ticker: str, start_date: date = None, end_date: date = None) -> List[Tuple[date, float]]:
        """
        Get split history for ticker.
        Returns list of (split_date, ratio) tuples.
        """
        db = get_db()
        if start_date and end_date:
            rows = db.query_sqlite(
                "SELECT split_date, ratio FROM splits WHERE ticker = ? AND split_date BETWEEN ? AND ? ORDER BY split_date",
                (ticker, start_date, end_date)
            )
        else:
            rows = db.query_sqlite(
                "SELECT split_date, ratio FROM splits WHERE ticker = ? ORDER BY split_date",
                (ticker,)
            )
        return [(row['split_date'], row['ratio']) for row in rows]
    
    def set_splits(self, ticker: str, splits: List[Tuple[date, float]]):
        """Store multiple splits for a ticker."""
        for split_date, ratio in splits:
            set_split(ticker, split_date, ratio)
    
    def set_split(self, ticker: str, split_date: date, ratio: float):
        """Store split."""
        return set_split(ticker, split_date, ratio)
    
    def clear_cache(self):
        """Clear all market data cache (prices, fx_rates, but not trades)."""
        db = get_db()
        db.execute_sqlite("DELETE FROM prices")
        db.execute_sqlite("DELETE FROM fx_rates")
        logger.info("Market data cache cleared (prices + fx_rates)")


# Singleton for compatibility
_cache_instance = None

def get_market_cache() -> MarketDataCache:
    """Get market cache instance (compatibility wrapper)."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MarketDataCache()
        # Ensure schema is initialized
        get_db().init_schema()
        get_db().init_schema()
        create_currency_table() # Ensure new table exists
        create_blacklist_table() # Ensure blacklist table exists
    return _cache_instance
