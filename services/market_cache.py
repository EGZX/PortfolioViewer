"""
Market Data Cache with SQLite

Stores historical prices, split data, FX rates, and ISIN mappings to minimize API calls.
"""

import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import os

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class MarketDataCache:
    """
    SQLite-based cache for market data.
    
    Tables:
    - prices: Current and historical prices
    - splits: Stock split events
    - fx_rates: Historical exchange rates
    - isin_map: ISIN to Ticker resolution
    """
    
    def __init__(self, db_path: str = "data/market_cache.db"):
        """
        Initialize market data cache.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a configured database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Create database tables if they don't exist."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            
            # Enable WAL mode for concurrency
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            # Prices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    ticker TEXT NOT NULL,
                    date DATE NOT NULL,
                    price REAL NOT NULL,
                    source TEXT DEFAULT 'yfinance',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, date)
                )
            """)
            
            # Splits table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS splits (
                    ticker TEXT NOT NULL,
                    split_date DATE NOT NULL,
                    ratio REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, split_date)
                )
            """)
            
            # FX Rates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fx_rates (
                    from_curr TEXT NOT NULL,
                    to_curr TEXT NOT NULL,
                    date DATE NOT NULL,
                    rate REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (from_curr, to_curr, date)
                )
            """)
            
            # ISIN Mapping table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS isin_map (
                    isin TEXT NOT NULL,
                    ticker TEXT,
                    source TEXT DEFAULT 'openfigi',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (isin)
                )
            """)
            
            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_ticker ON prices(ticker, date DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_splits_ticker ON splits(ticker, split_date DESC)")
            
            conn.commit()
            logger.info(f"Initialized market data cache at {self.db_path}")
    
    # ==================== Price Methods ====================
    
    def get_price(self, ticker: str, target_date: Optional[date] = None) -> Optional[float]:
        """Get cached price for a ticker on a specific date."""
        if target_date is None:
            target_date = date.today()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price FROM prices WHERE ticker = ? AND date = ?",
                (ticker, target_date)
            )
            result = cursor.fetchone()
            return float(result[0]) if result else None
    
    def set_price(self, ticker: str, price: float, target_date: Optional[date] = None, source: str = "yfinance"):
        """Cache a price for a ticker on a specific date."""
        if target_date is None:
            target_date = date.today()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO prices (ticker, date, price, source) VALUES (?, ?, ?, ?)",
                (ticker, target_date, price, source)
            )
            conn.commit()
    
    def get_prices_batch(self, tickers: List[str], target_date: Optional[date] = None) -> Dict[str, Optional[float]]:
        """Get cached prices for multiple tickers."""
        if target_date is None:
            target_date = date.today()
        
        prices = {t: None for t in tickers}
        
        if not tickers:
            return prices

        with self._get_conn() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(tickers))
            cursor.execute(
                f"SELECT ticker, price FROM prices WHERE ticker IN ({placeholders}) AND date = ?",
                (*tickers, target_date)
            )
            
            for ticker, price in cursor.fetchall():
                prices[ticker] = float(price)
        
        hit_count = sum(1 for p in prices.values() if p is not None)
        logger.debug(f"Batch cache lookup: {hit_count}/{len(tickers)} hits on {target_date}")
        return prices
    
    # ==================== Split Methods ====================
    
    def get_splits(self, ticker: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Tuple[date, float]]:
        """Get cached split events for a ticker in a date range."""
        if start_date is None:
            start_date = date.today() - timedelta(days=365 * 10)
        if end_date is None:
            end_date = date.today()
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT split_date, ratio FROM splits 
                WHERE ticker = ? AND split_date BETWEEN ? AND ?
                ORDER BY split_date DESC
                """,
                (ticker, start_date, end_date)
            )
            return [(datetime.strptime(row[0], '%Y-%m-%d').date(), float(row[1])) for row in cursor.fetchall()]
    
    def set_splits(self, ticker: str, splits: List[Tuple[date, float]]):
        """Cache split events for a ticker."""
        if not splits:
            return

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR REPLACE INTO splits (ticker, split_date, ratio) VALUES (?, ?, ?)",
                [(ticker, split_date, ratio) for split_date, ratio in splits]
            )
            conn.commit()
            logger.info(f"Cached {len(splits)} splits for {ticker}")
    
    def clear_splits(self, ticker: str) -> int:
        """Clear all cached split data for a specific ticker."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM splits WHERE ticker = ?", (ticker,))
            conn.commit()
            logger.info(f"Cleared {cursor.rowcount} split records for {ticker}")
            return cursor.rowcount

    # ==================== FX Methods ====================

    def get_fx_rate(self, from_curr: str, to_curr: str, target_date: date) -> Optional[float]:
        """Get cached FX rate."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT rate FROM fx_rates WHERE from_curr = ? AND to_curr = ? AND date = ?",
                (from_curr, to_curr, target_date)
            )
            result = cursor.fetchone()
            return float(result[0]) if result else None

    def set_fx_rate(self, from_curr: str, to_curr: str, target_date: date, rate: float):
        """Cache FX rate."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO fx_rates (from_curr, to_curr, date, rate) VALUES (?, ?, ?, ?)",
                (from_curr, to_curr, target_date, rate)
            )
            conn.commit()

    # ==================== ISIN Map Methods ====================

    def get_isin_mapping(self, isin: str) -> Optional[str]:
        """Get cached ISIN to ticker mapping."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ticker FROM isin_map WHERE isin = ?",
                (isin,)
            )
            result = cursor.fetchone()
            # result[0] can be None if we cached a "not found" state (though usually we cache actual values)
            # If we want to support negative caching, we'd need to handle that. 
            # For now assume mostly positive caching or None if missing.
            return result[0] if result else None

    def set_isin_mapping(self, isin: str, ticker: Optional[str], source: str = 'openfigi'):
        """Cache ISIN to ticker mapping."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO isin_map (isin, ticker, source) VALUES (?, ?, ?)",
                (isin, ticker, source)
            )
            conn.commit()

# Global cache instance
_cache_instance: Optional[MarketDataCache] = None 


def get_market_cache() -> MarketDataCache:
    """Get or create global market cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MarketDataCache()
    return _cache_instance
