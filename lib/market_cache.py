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
    
    def get_prices_batch(self, tickers: List[str], target_date: date) -> Dict[str, Optional[float]]:
        return get_prices_batch(tickers, target_date)
    
    def set_prices_batch(self, prices: List[Tuple[str, date, float, str]]):
        return set_prices_batch(prices)
    
    def get_historical_prices(self, tickers: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        return get_historical_prices(tickers, start_date, end_date)
    
    def get_fx_rate(self, from_curr: str, to_curr: str, target_date: date) -> Optional[float]:
        return get_fx_rate(from_curr, to_curr, target_date)
    
    def set_fx_rate(self, from_curr: str, to_curr: str, target_date: date, rate: float):
        return set_fx_rate(from_curr, to_curr, target_date, rate)


# Singleton for compatibility
_cache_instance = None

def get_market_cache() -> MarketDataCache:
    """Get market cache instance (compatibility wrapper)."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MarketDataCache()
        # Ensure schema is initialized
        get_db().init_schema()
    return _cache_instance
