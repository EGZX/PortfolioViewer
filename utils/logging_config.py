"""
Enhanced Logging Configuration

Provides professional-grade logging with:
- Structured output for parsing
- Performance tracking
- Context preservation
- Environment-based levels
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import os


class StructuredFormatter(logging.Formatter):
    """
    Structured log formatter for better parsing and debugging.
    
    Format: [TIMESTAMP] [LEVEL] [MODULE:FUNCTION:LINE] MESSAGE {context}
    """
    
    def format(self, record: logging.LogRecord) -> str:
        # Add custom attributes if missing
        if not hasattr(record, 'user_context'):
            record.user_context = ''
        
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Format location
        location = f"{record.module}:{record.funcName}:{record.lineno}"
        
        # Build base message
        base_msg = f"[{timestamp}] [{record.levelname:8s}] [{location}] {record.getMessage()}"
        
        # Add exception info if present
        if record.exc_info:
            base_msg += f"\n{self.formatException(record.exc_info)}"
        
        # Add context if present
        if record.user_context:
            base_msg += f" {record.user_context}"
        
        return base_msg


class PerformanceLogger:
    """Context manager for performance logging."""
    
    def __init__(self, logger: logging.Logger, operation: str, threshold_ms: float = 1000):
        self.logger = logger
        self.operation = operation
        self.threshold_ms = threshold_ms
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (datetime.now() - self.start_time).total_seconds() * 1000
            
            if duration_ms > self.threshold_ms:
                self.logger.warning(f"SLOW: {self.operation} took {duration_ms:.1f}ms")
            else:
                self.logger.debug(f"{self.operation} took {duration_ms:.1f}ms")


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up a logger with enhanced formatting and optional file output.
    
    Args:
        name: Logger name (usually __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env var or INFO
        log_file: Optional file path for logs
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Determine log level
    if level is None:
        level = os.getenv('LOG_LEVEL', 'INFO').upper()
    
    log_level = getattr(logging, level, logging.INFO)
    logger.setLevel(log_level)
    
    # Console handler with structured formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(StructuredFormatter())
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_perf_logger(logger: logging.Logger, operation: str, threshold_ms: float = 1000):
    """
    Get a performance logger context manager.
    
    Usage:
        with get_perf_logger(logger, "fetch_prices", threshold_ms=500):
            # Your code here
            prices = fetch_prices(tickers)
    
    Args:
        logger: Logger instance
        operation: Operation name for logging
        threshold_ms: Milliseconds threshold for SLOW warning
    
    Returns:
        PerformanceLogger context manager
    """
    return PerformanceLogger(logger, operation, threshold_ms)


# Module-level convenience function
def log_dataframe_info(logger: logging.Logger, df, name: str = "DataFrame"):
    """
    Log useful DataFrame statistics.
    
    Args:
        logger: Logger instance
        df: Pandas DataFrame
        name: Name for the DataFrame in logs
    """
    if df is None:
        logger.warning(f"{name} is None")
        return
    
    if df.empty:
        logger.info(f"{name} is empty (0 rows)")
    else:
        logger.info(f"{name}: {len(df)} rows, {len(df.columns)} columns")
        
        # Log memory usage for large DataFrames
        memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
        if memory_mb > 10:
            logger.warning(f"{name} using {memory_mb:.1f}MB memory")
