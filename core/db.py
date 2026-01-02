"""
Database Connection Manager - "The Glue"

Provides unified access to both SQLite (for trades/settings) and DuckDB 
(for analytical queries across SQLite + Parquet files).

Architecture:
- SQLite: Transactional data (trades, settings, audit logs)
- Parquet: Time-series market data (OHLCV)
- DuckDB: Query engine that can join both

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import logging

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    logging.warning("DuckDB not available. Install with: pip install duckdb")

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages database connections for the portfolio platform.
    
    Provides:
    - SQLite connection for transactional data
    - DuckDB connection for analytical queries
    - Unified query interface
    """
    
    def __init__(self, data_dir: Path = None):
        """
        Initialize database manager.
        
        Args:
            data_dir: Path to data directory (defaults to ./data)
        """
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # Database paths
        self.sqlite_path = self.data_dir / "portfolio.db"
        self.market_cache_dir = self.data_dir / "market_cache"
        self.market_cache_dir.mkdir(exist_ok=True)
        
        # Connections (lazy loaded)
        self._sqlite_conn: Optional[sqlite3.Connection] = None
        self._duckdb_conn: Optional[Any] = None  # duckdb.DuckDBPyConnection
    
    @property
    def sqlite(self) -> sqlite3.Connection:
        """Get SQLite connection (creates if needed)."""
        if self._sqlite_conn is None:
            self._sqlite_conn = sqlite3.connect(
                str(self.sqlite_path),
                detect_types=sqlite3.PARSE_DECLTYPES
            )
            self._sqlite_conn.row_factory = sqlite3.Row
            logger.info(f"SQLite connection opened: {self.sqlite_path}")
        return self._sqlite_conn
    
    @property
    def duckdb(self) -> Any:
        """
        Get DuckDB connection (creates if needed).
        
        Automatically ATTACHes the SQLite database for cleaner queries.
        
        Example:
            # Instead of: SELECT * FROM sqlite_scan('/path/to/portfolio.db', 'trades')
            # You can use: SELECT * FROM portfolio.trades
        """
        if not DUCKDB_AVAILABLE:
            raise RuntimeError("DuckDB not installed. Run: pip install duckdb")
        
        if self._duckdb_conn is None:
            self._duckdb_conn = duckdb.connect(":memory:")
            
            # ATTACH SQLite database for cleaner queries
            try:
                attach_sql = f"ATTACH '{self.sqlite_path}' AS portfolio (TYPE SQLITE);"
                self._duckdb_conn.execute(attach_sql)
                logger.info(f"DuckDB in-memory connection opened, attached SQLite: {self.sqlite_path}")
            except Exception as e:
                logger.warning(f"Could not ATTACH SQLite to DuckDB: {e}")
                logger.info("DuckDB in-memory connection opened (no ATTACH)")
        
        return self._duckdb_conn
    
    def query_sqlite(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """
        Execute SQL query on SQLite database.
        
        Args:
            sql: SQL query string
            params: Query parameters (for parameterized queries)
        
        Returns:
            List of rows as dictionaries
        """
        cursor = self.sqlite.execute(sql, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def execute_sqlite(self, sql: str, params: tuple = ()) -> int:
        """
        Execute SQL statement on SQLite (INSERT, UPDATE, DELETE).
        
        Args:
            sql: SQL statement
            params: Statement parameters
        
        Returns:
            Number of affected rows
        """
        cursor = self.sqlite.execute(sql, params)
        self.sqlite.commit()
        return cursor.rowcount
    
    def query_duckdb(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute analytical query with DuckDB.
        
        The SQLite database is automatically ATTACHed as 'portfolio'.
        
        Can query:
        - SQLite tables: SELECT * FROM portfolio.trades
        - Parquet files: SELECT * FROM read_parquet('data/market_cache/*.parquet')
        - Join both sources
        
        Args:
            sql: DuckDB SQL query
        
        Returns:
            List of rows as dictionaries
        
        Example:
            >>> db.query_duckdb(\"\"\"
            ...     SELECT t.ticker, COUNT(*) as num_trades
            ...     FROM portfolio.trades t
            ...     WHERE t.date > '2024-01-01'
            ...     GROUP BY t.ticker
            ... \"\"\")
        
        Note:
            Automatically runs WAL checkpoint to ensure DuckDB sees latest data.
        """
        # CRITICAL: Checkpoint WAL before DuckDB reads SQLite
        self.checkpoint()
        
        result = self.duckdb.execute(sql).fetchall()
        columns = [desc[0] for desc in self.duckdb.description]
        return [dict(zip(columns, row)) for row in result]
    
    def get_parquet_path(self, ticker: str) -> Path:
        """
        Get path for ticker's Parquet file.
        
        Args:
            ticker: Ticker symbol
        
        Returns:
            Path to parquet file (may not exist yet)
        """
        # Sanitize ticker for filename
        safe_ticker = ticker.replace('/', '_').replace('\\', '_')
        return self.market_cache_dir / f"{safe_ticker}.parquet"
    
    def init_schema(self):
        """
        Initialize database schema.
        
        Creates tables:
        - trades: Transaction history
        - settings: Application settings
        - tax_audit_log: Immutable tax calculation audit trail
        - prices: Market data cache (current and historical prices)
        - splits: Stock split events
        - fx_rates: Historical exchange rates
        - isin_map: ISIN to Ticker resolution
        """
        schema_sql = """
        -- Trades table (replaces transactions.db logic)
        -- NOTE: Using REAL for shares/price/total - acceptable for this use case
        -- but aware of floating point precision limits. For strict financial
        -- accuracy, consider INTEGER (cents) or Decimal in Python validation.
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            ticker TEXT,
            isin TEXT,
            name TEXT,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            fees REAL DEFAULT 0,
            total REAL NOT NULL,
            currency TEXT NOT NULL,
            fx_rate REAL DEFAULT 1.0,
            broker TEXT,
            asset_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);
        CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
        CREATE INDEX IF NOT EXISTS idx_trades_type ON trades(type);
        
        -- Settings table
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Tax audit log (append-only, immutable)
        CREATE TABLE IF NOT EXISTS tax_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            calculation_hash TEXT NOT NULL,
            strategy_version TEXT NOT NULL,  -- e.g., 'v2.0-AT-E1kv'
            inputs TEXT NOT NULL,  -- JSON
            outputs TEXT NOT NULL, -- JSON
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_tax_audit_timestamp ON tax_audit_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_tax_audit_event ON tax_audit_log(event_id);
        
        -- Market Data: Prices table
        CREATE TABLE IF NOT EXISTS prices (
            ticker TEXT NOT NULL,
            date DATE NOT NULL,
            price REAL NOT NULL,
            source TEXT DEFAULT 'yfinance',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, date)
        );
        
        CREATE INDEX IF NOT EXISTS idx_prices_ticker ON prices(ticker);
        CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
        
        -- Market Data: Splits table
        CREATE TABLE IF NOT EXISTS splits (
            ticker TEXT NOT NULL,
            split_date DATE NOT NULL,
            ratio REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticker, split_date)
        );
        
        CREATE INDEX IF NOT EXISTS idx_splits_ticker ON splits(ticker);
        
        -- Market Data: FX Rates table
        CREATE TABLE IF NOT EXISTS fx_rates (
            from_curr TEXT NOT NULL,
            to_curr TEXT NOT NULL,
            date DATE NOT NULL,
            rate REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (from_curr, to_curr, date)
        );
        
        CREATE INDEX IF NOT EXISTS idx_fx_rates_pair ON fx_rates(from_curr, to_curr);
        
        -- Market Data: ISIN Mapping table
        CREATE TABLE IF NOT EXISTS isin_map (
            isin TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            name TEXT,
            exchange TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_isin_map_ticker ON isin_map(ticker);
        """
        
        # Enable WAL mode for better concurrency
        self.sqlite.execute("PRAGMA journal_mode=WAL;")
        self.sqlite.executescript(schema_sql)
        self.sqlite.commit()
        logger.info("Database schema initialized (trades + market data)")
    
    def checkpoint(self):
        """
        Force WAL checkpoint to ensure DuckDB can read latest data.
        
        CRITICAL: DuckDB may not see uncommitted WAL changes without this.
        Call before running analytical DuckDB queries.
        """
        try:
            self.sqlite.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            self.sqlite.commit()
            logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")
    
    def close(self):
        """Close all database connections."""
        if self._sqlite_conn:
            self._sqlite_conn.close()
            self._sqlite_conn = None
            logger.info("SQLite connection closed")
        
        if self._duckdb_conn:
            self._duckdb_conn.close()
            self._duckdb_conn = None
            logger.info("DuckDB connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


# Thread-local storage for database connections
import threading
_thread_local = threading.local()


def get_db(data_dir: Path = None) -> DatabaseManager:
    """
    Get thread-local DatabaseManager instance.
    
    Each thread gets its own database connection to avoid SQLite threading issues.
    
    Args:
        data_dir: Data directory path (optional)
    
    Returns:
        DatabaseManager instance for current thread
    """
    if not hasattr(_thread_local, 'db_instance'):
        _thread_local.db_instance = DatabaseManager(data_dir)
    return _thread_local.db_instance
