"""
Market Data Cache with SQLite.

Stores historical prices, split data, FX rates, and ISIN mappings to minimize API calls.
"""

import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import os
import pandas as pd
import streamlit as st
from cryptography.fernet import Fernet

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
        
        # Initialize encryption
        self.fernet = None
        try:
            # Check for key in secrets (nested under passwords or top level)
            secrets = st.secrets.get("passwords", {}) if "passwords" in st.secrets else st.secrets
            key = secrets.get("MARKET_CACHE_ENCRYPTION_KEY")
            
            if key:
                self.fernet = Fernet(key)
                logger.info("Cache encryption enabled")
            else:
                logger.info("Cache encryption disabled (no key found)")
        except Exception as e:
            logger.warning(f"Failed to initialize encryption: {e}")
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a configured database connection."""
        # Timeout increased to 30s to handle concurrent writes
        return sqlite3.connect(self.db_path, timeout=30.0)

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
            
            # Transactions cache table (stores last uploaded CSV)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    csv_content TEXT NOT NULL,
                    filename TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        """
        Get cached prices for multiple tickers.
        If target_date is provided, gets prices for that specific date.
        If target_date is None, gets the LATEST available price for each ticker.
        """
        prices = {t: None for t in tickers}
        
        if not tickers:
            return prices

        with self._get_conn() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(tickers))
            
            if target_date:
                # Specific date query
                cursor.execute(
                    f"SELECT ticker, price FROM prices WHERE ticker IN ({placeholders}) AND date = ?",
                    (*tickers, target_date)
                )
            else:
                # Latest price query using window function
                # We want the price from the most recent date for each ticker
                query = f"""
                    WITH LatestPrices AS (
                        SELECT 
                            ticker, 
                            price,
                            ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) as rn
                        FROM prices 
                        WHERE ticker IN ({placeholders})
                    )
                    SELECT ticker, price 
                    FROM LatestPrices 
                    WHERE rn = 1
                """
                cursor.execute(query, tickers)
            
            for ticker, price in cursor.fetchall():
                prices[ticker] = float(price)
        
        hit_count = sum(1 for p in prices.values() if p is not None)
        date_msg = f"on {target_date}" if target_date else "(latest)"
        logger.debug(f"Batch cache lookup: {hit_count}/{len(tickers)} hits {date_msg}")
        return prices
    
    def get_latest_prices(self, tickers: List[str]) -> Dict[str, Optional[float]]:
        """Convenience alias for get_prices_batch(tickers, None)."""
        return self.get_prices_batch(tickers, target_date=None)
        
    def get_historical_prices(self, tickers: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        """
        Get cached historical prices for multiple tickers in a date range.
        Returns a DataFrame compatible with yfinance structure (Date index, Ticker columns).
        """
        if not tickers:
            return pd.DataFrame()
            
        with self._get_conn() as conn:
            # Optimize read with pandas directly
            placeholders = ','.join('?' * len(tickers))
            query = f"""
                SELECT date, ticker, price 
                FROM prices 
                WHERE ticker IN ({placeholders}) 
                AND date BETWEEN ? AND ?
            """
            params = (*tickers, start_date, end_date)
            
            try:
                df = pd.read_sql_query(query, conn, params=params)
                
                if df.empty:
                    return pd.DataFrame()
                
                # Pivot to match yfinance structure: Index=Date, Cols=Tickers, Vals=Price
                df['date'] = pd.to_datetime(df['date'])
                pivot_df = df.pivot(index='date', columns='ticker', values='price')
                
                return pivot_df
                
            except Exception as e:
                logger.error(f"Failed to read historical prices from cache: {e}")
                return pd.DataFrame()

    def set_prices_batch(self, prices_data: List[Tuple[str, date, float, str]]):
        """
        Batch insert multiple price records.
        Args:
            prices_data: List of (ticker, date, price, source) tuples
        """
        if not prices_data:
            return
            
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR REPLACE INTO prices (ticker, date, price, source) VALUES (?, ?, ?, ?)",
                prices_data
            )
            conn.commit()
            logger.info(f"Bulk cached {len(prices_data)} price records")
    
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

    # ==================== Transaction Cache Methods ====================

    def save_transactions_csv(self, csv_content: str, filename: str = "uploaded.csv"):
        """
        Save CSV content to cache for auto-loading.
        Encrypts content if encryption is enabled.
        """
        content_to_save = csv_content
        
        if self.fernet:
            try:
                # Encrypt
                content_to_save = self.fernet.encrypt(csv_content.encode('utf-8')).decode('utf-8')
                logger.info("Encrypted transaction data before caching")
            except Exception as e:
                logger.error(f"Encryption failed: {e}")
                # Don't save unencrypted if encryption failed
                return

        with self._get_conn() as conn:
            cursor = conn.cursor()
            # Delete old cached transactions (keep only latest)
            cursor.execute("DELETE FROM transactions_cache")
            # Insert new
            cursor.execute(
                "INSERT INTO transactions_cache (csv_content, filename) VALUES (?, ?)",
                (content_to_save, filename)
            )
            conn.commit()
            logger.info(f"Saved transactions CSV to cache: {filename}")

    def get_last_transactions_csv(self) -> Optional[Tuple[str, str, datetime]]:
        """
        Get last cached CSV content.
        Decrypts content if encryption is enabled.
        
        Returns:
            Tuple of (csv_content, filename, uploaded_at) or None if no cache
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT csv_content, filename, uploaded_at FROM transactions_cache ORDER BY uploaded_at DESC LIMIT 1"
            )
            result = cursor.fetchone()
            
            if not result:
                return None
                
            csv_content, filename, uploaded_at_str = result
            
            # Decrypt if enabled
            if self.fernet:
                try:
                    csv_content = self.fernet.decrypt(csv_content.encode('utf-8')).decode('utf-8')
                    logger.info("Decrypted transaction data from cache")
                except Exception as e:
                    # Fallback: try return as is if it looks like plain text
                    if csv_content.strip().startswith(('Date', 'Datum', '"Date"', '"Datum"')):
                         logger.warning("Loaded plain text cache with encryption key present")
                    else:
                         logger.error(f"Decryption failed: {e}")
                         return None
            
            return (csv_content, filename, datetime.fromisoformat(uploaded_at_str))

# Global cache instance
_cache_instance: Optional[MarketDataCache] = None 


def get_market_cache() -> MarketDataCache:
    """Get or create global market cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MarketDataCache()
    return _cache_instance
