"""
Market Data Cache with SQLite and Encryption

Stores historical prices and split data to minimize API calls.
Encrypts data if ENCRYPTION_KEY is set in environment (for public repos).
"""

import sqlite3
import json
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from decimal import Decimal
import os
from cryptography.fernet import Fernet
import base64

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class MarketDataCache:
    """
    SQLite-based cache for market data with optional encryption.
    
    Tables:
    - prices: Current and historical prices
    - splits: Stock split events
    """
    
    def __init__(self, db_path: str = "data/market_cache.db", encrypt: bool = True):
        """
        Initialize market data cache.
        
        Args:
            db_path: Path to SQLite database file
            encrypt: Whether to encrypt sensitive data (default: True)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Setup encryption if enabled and key is available
        self.encrypt = encrypt
        self.cipher = None
        
        if encrypt:
            encryption_key = os.getenv('MARKET_CACHE_ENCRYPTION_KEY')
            if encryption_key:
                self.cipher = Fernet(encryption_key.encode())
                logger.info("Market cache encryption enabled")
            else:
                logger.warning("Encryption requested but MARKET_CACHE_ENCRYPTION_KEY not set. Cache will be unencrypted.")
        
        self._init_db()
    
    def _init_db(self):
        """Create database tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
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
            
            # Create indexes for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prices_ticker 
                ON prices(ticker, date DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_splits_ticker 
                ON splits(ticker, split_date DESC)
            """)
            
            conn.commit()
            logger.info(f"Initialized market data cache at {self.db_path}")
    
    def _encrypt_data(self, data: str) -> str:
        """Encrypt data if encryption is enabled."""
        if self.cipher:
            return self.cipher.encrypt(data.encode()).decode()
        return data
    
    def _decrypt_data(self, data: str) -> str:
        """Decrypt data if encryption is enabled."""
        if self.cipher:
            return self.cipher.decrypt(data.encode()).decode()
        return data
    
    # ==================== Price Methods ====================
    
    def get_price(self, ticker: str, target_date: Optional[date] = None) -> Optional[float]:
        """
        Get cached price for a ticker on a specific date.
        
        Args:
            ticker: Ticker symbol
            target_date: Date to fetch price for (default: today)
        
        Returns:
            Price as float or None if not cached
        """
        if target_date is None:
            target_date = date.today()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT price FROM prices WHERE ticker = ? AND date = ?",
                (ticker, target_date)
            )
            result = cursor.fetchone()
            
            if result:
                logger.debug(f"Cache HIT: {ticker} on {target_date} = {result[0]}")
                return float(result[0])
            
            logger.debug(f"Cache MISS: {ticker} on {target_date}")
            return None
    
    def set_price(self, ticker: str, price: float, target_date: Optional[date] = None, source: str = "yfinance"):
        """
        Cache a price for a ticker on a specific date.
        
        Args:
            ticker: Ticker symbol
            price: Price value
            target_date: Date (default: today)
            source: Data source name
        """
        if target_date is None:
            target_date = date.today()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO prices (ticker, date, price, source)
                VALUES (?, ?, ?, ?)
                """,
                (ticker, target_date, price, source)
            )
            conn.commit()
            logger.debug(f"Cached price: {ticker} on {target_date} = {price} (source: {source})")
    
    def get_prices_batch(self, tickers: List[str], target_date: Optional[date] = None) -> Dict[str, Optional[float]]:
        """
        Get cached prices for multiple tickers.
        
        Args:
            tickers: List of ticker symbols
            target_date: Date to fetch prices for (default: today)
        
        Returns:
            Dictionary mapping ticker to price (None if not cached)
        """
        if target_date is None:
            target_date = date.today()
        
        prices = {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(tickers))
            cursor.execute(
                f"""
                SELECT ticker, price FROM prices 
                WHERE ticker IN ({placeholders}) AND date = ?
                """,
                (*tickers, target_date)
            )
            
            results = cursor.fetchall()
            for ticker, price in results:
                prices[ticker] = float(price)
            
            # Fill in None for missing tickers
            for ticker in tickers:
                if ticker not in prices:
                    prices[ticker] = None
        
        hit_count = sum(1 for p in prices.values() if p is not None)
        logger.info(f"Batch cache lookup: {hit_count}/{len(tickers)} hits on {target_date}")
        
        return prices
    
    def set_prices_batch(self, prices: Dict[str, float], target_date: Optional[date] = None, source: str = "yfinance"):
        """
        Cache prices for multiple tickers.
        
        Args:
            prices: Dictionary mapping ticker to price
            target_date: Date (default: today)
            source: Data source name
        """
        if target_date is None:
            target_date = date.today()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR REPLACE INTO prices (ticker, date, price, source)
                VALUES (?, ?, ?, ?)
                """,
                [(ticker, target_date, price, source) for ticker, price in prices.items()]
            )
            conn.commit()
            logger.info(f"Cached {len(prices)} prices on {target_date}")
    
    def is_price_fresh(self, ticker: str, max_age_hours: int = 24) -> bool:
        """
        Check if cached price is fresh enough.
        
        Args:
            ticker: Ticker symbol
            max_age_hours: Maximum age in hours before considered stale
        
        Returns:
            True if fresh price exists
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT created_at FROM prices 
                WHERE ticker = ? AND date = DATE('now')
                ORDER BY created_at DESC LIMIT 1
                """,
                (ticker,)
            )
            result = cursor.fetchone()
            
            if result:
                cached_time = datetime.fromisoformat(result[0])
                age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                return age_hours < max_age_hours
            
            return False
    
    # ==================== Split Methods ====================
    
    def get_splits(self, ticker: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Tuple[date, float]]:
        """
        Get cached split events for a ticker in a date range.
        
        Args:
            ticker: Ticker symbol
            start_date: Start date (default: 10 years ago)
            end_date: End date (default: today)
        
        Returns:
            List of (split_date, ratio) tuples
        """
        if start_date is None:
            start_date = date.today() - timedelta(days=365 * 10)
        if end_date is None:
            end_date = date.today()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT split_date, ratio FROM splits 
                WHERE ticker = ? AND split_date BETWEEN ? AND ?
                ORDER BY split_date DESC
                """,
                (ticker, start_date, end_date)
            )
            results = cursor.fetchall()
            
            splits = [(datetime.strptime(split_date, '%Y-%m-%d').date(), float(ratio)) 
                     for split_date, ratio in results]
            
            if splits:
                logger.debug(f"Cache HIT: {len(splits)} splits for {ticker}")
            
            return splits
    
    def set_splits(self, ticker: str, splits: List[Tuple[date, float]]):
        """
        Cache split events for a ticker.
        
        Args:
            ticker: Ticker symbol
            splits: List of (split_date, ratio) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR REPLACE INTO splits (ticker, split_date, ratio)
                VALUES (?, ?, ?)
                """,
                [(ticker, split_date, ratio) for split_date, ratio in splits]
            )
            conn.commit()
            logger.info(f"Cached {len(splits)} splits for {ticker}")
    
    def clear_splits(self, ticker: str):
        """
        Clear all cached split data for a specific ticker.
        Use this to remove incorrect split data.
        
        Args:
            ticker: Ticker symbol
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM splits WHERE ticker = ?", (ticker,))
            deleted_count = cursor.rowcount
            conn.commit()
            logger.info(f"Cleared {deleted_count} split records for {ticker}")
            return deleted_count
    
    def clear_old_data(self, days: int = 365):
        """
        Clear cached data older than specified days.
        
        Args:
            days: Age threshold in days
        """
        cutoff_date = date.today() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM prices WHERE date < ?", (cutoff_date,))
            prices_deleted = cursor.rowcount
            
            # Keep splits indefinitely (they're permanent events)
            
            conn.commit()
            logger.info(f"Cleared {prices_deleted} old price records (older than {cutoff_date})")
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM prices")
            price_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT ticker) FROM prices")
            ticker_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM splits")
            split_count = cursor.fetchone()[0]
            
            return {
                'total_prices': price_count,
                'unique_tickers': ticker_count,
                'total_splits': split_count,
            }


# Global cache instance
_cache_instance: Optional[MarketDataCache] = None


def get_market_cache() -> MarketDataCache:
    """Get or create global market cache instance."""
    global _cache_instance
    
    if _cache_instance is None:
        _cache_instance = MarketDataCache()
    
    return _cache_instance
