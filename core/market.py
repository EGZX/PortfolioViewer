"""
Market Data Module - Parquet Storage Layer

Fetches market data and stores it efficiently in Parquet format.
One Parquet file per ticker for optimal columnar storage and query performance.

Architecture:
- Fetches OHLCV data from existing market_data service
- Stores in data/market_cache/{ticker}.parquet
- Can be queried via DuckDB for analytics

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    import pandas as pd

try:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    PARQUET_AVAILABLE = True
except ImportError:
    pd = None
    PARQUET_AVAILABLE = False
    logging.warning("Parquet support not available. Install with: pip install pyarrow")

logger = logging.getLogger(__name__)


class MarketDataParquet:
    """
    Market data storage using Parquet format.
    
    Features:
    - Efficient columnar storage for time-series data
    - One file per ticker (e.g., AAPL.parquet)
    - Compatible with DuckDB queries
    - Incremental updates
    """
    
    def __init__(self, cache_dir: Path = None):
        """
        Initialize market data Parquet store.
        
        Args:
            cache_dir: Directory for Parquet files (defaults to data/market_cache)
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent / "data" / "market_cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        if not PARQUET_AVAILABLE:
            logger.warning("Parquet support unavailable - install pyarrow")
    
    def get_parquet_path(self, ticker: str) -> Path:
        """Get path for ticker's Parquet file."""
        safe_ticker = ticker.replace('/', '_').replace('\\', '_')
        return self.cache_dir / f"{safe_ticker}.parquet"
    
    def save_price_data(
        self,
        ticker: str,
        data: "pd.DataFrame",
        append: bool = False
    ) -> bool:
        """
        Save price data to Parquet file.
        
        Args:
            ticker: Ticker symbol
            data: DataFrame with columns: date, open, high, low, close, volume
            append: If True, merge with existing data (deduplicates by date)
        
        Returns:
            True if successful
        """
        if not PARQUET_AVAILABLE:
            logger.error("Parquet support not available")
            return False
        
        if data.empty:
            logger.warning(f"Empty data for {ticker}, skipping save")
            return False
        
        try:
            path = self.get_parquet_path(ticker)
            
            # Ensure date column is datetime
            if 'date' not in data.columns:
                data = data.reset_index()
            
            if not pd.api.types.is_datetime64_any_dtype(data['date']):
                data['date'] = pd.to_datetime(data['date'])
            
            # Standard columns
            required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
            for col in required_cols:
                if col not in data.columns:
                    if col == 'volume':
                        data[col] = 0  # Default volume
                    else:
                        logger.error(f"Missing required column: {col}")
                        return False
            
            # Select only required columns
            data = data[required_cols].copy()
            
            if append and path.exists():
                # Merge with existing data
                existing = pd.read_parquet(path)
                data = pd.concat([existing, data]).drop_duplicates(subset=['date'], keep='last')
            
            # Sort by date
            data = data.sort_values('date')
            
            # Write to Parquet
            data.to_parquet(path, engine='pyarrow', compression='snappy', index=False)
            
            logger.info(f"Saved {len(data)} records for {ticker} to Parquet")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save Parquet for {ticker}: {e}")
            return False
    
    def load_price_data(
        self,
        ticker: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Optional["pd.DataFrame"]:
        """
        Load price data from Parquet file.
        
        Args:
            ticker: Ticker symbol
            start_date: Optional start date filter
            end_date: Optional end date filter
        
        Returns:
            DataFrame with price data, or None if not found
        """
        if not PARQUET_AVAILABLE:
            return None
        
        try:
            path = self.get_parquet_path(ticker)
            
            if not path.exists():
                logger.debug(f"No Parquet file for {ticker}")
                return None
            
            # Read Parquet file
            df = pd.read_parquet(path)
            
            # Apply date filters
            if start_date:
                df = df[df['date'] >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df['date'] <= pd.Timestamp(end_date)]
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to load Parquet for {ticker}: {e}")
            return None
    
    def get_latest_price(self, ticker: str) -> Optional[float]:
        """
        Get most recent closing price for ticker.
        
        Args:
            ticker: Ticker symbol
        
        Returns:
            Latest close price, or None if not available
        """
        df = self.load_price_data(ticker)
        if df is not None and not df.empty:
            return float(df.iloc[-1]['close'])
        return None
    
    def get_price_at_date(self, ticker: str, target_date: date) -> Optional[float]:
        """
        Get closing price at specific date (or nearest prior date).
        
        Args:
            ticker: Ticker symbol
            target_date: Target date
        
        Returns:
            Close price at date, or None if not available
        """
        df = self.load_price_data(ticker, end_date=target_date)
        if df is not None and not df.empty:
            return float(df.iloc[-1]['close'])
        return None
    
    def has_data(self, ticker: str) -> bool:
        """Check if Parquet file exists for ticker."""
        return self.get_parquet_path(ticker).exists()
    
    def get_date_range(self, ticker: str) -> Optional[tuple]:
        """
        Get date range of available data.
        
        Args:
            ticker: Ticker symbol
        
        Returns:
            Tuple of (earliest_date, latest_date) or None
        """
        df = self.load_price_data(ticker)
        if df is not None and not df.empty:
            return (df['date'].min().date(), df['date'].max().date())
        return None
    
    def migrate_from_sqlite(self, sqlite_path: Path, ticker: str) -> bool:
        """
        Migrate market data from SQLite to Parquet.
        
        Args:
            sqlite_path: Path to SQLite database (e.g., market_cache.db)
            ticker: Ticker to migrate
        
        Returns:
            True if successful
        """
        try:
            import sqlite3
            
            conn = sqlite3.connect(str(sqlite_path))
            
            # Read from market_cache table (assuming it exists)
            query = f"""
                SELECT date, open, high, low, close, volume
                FROM market_cache
                WHERE ticker = ?
                ORDER BY date
            """
            
            df = pd.read_sql_query(query, conn, params=(ticker,))
            conn.close()
            
            if not df.empty:
                return self.save_price_data(ticker, df, append=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate {ticker} from SQLite: {e}")
            return False


# Global instance
_market_instance: Optional[MarketDataParquet] = None


def get_market_parquet(cache_dir: Path = None) -> MarketDataParquet:
    """
    Get global MarketDataParquet instance.
    
    Args:
        cache_dir: Cache directory (optional)
    
    Returns:
        MarketDataParquet singleton
    """
    global _market_instance
    if _market_instance is None:
        _market_instance = MarketDataParquet(cache_dir)
    return _market_instance
