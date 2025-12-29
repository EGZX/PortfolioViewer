"""
Historical FX Rate Service

Provides date-specific foreign exchange rates with caching for accurate
multi-currency portfolio calculations.
"""

import yfinance as yf
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict
import streamlit as st

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class FXRateService:
    """
    Manages historical FX rate lookup and caching.
    
    Features:
    - Historical rate lookup (not just current rates)
    - In-memory caching to avoid redundant API calls
    - Fallback to current rates when historical unavailable
    - Support for all major currency pairs via yfinance
    """
    
    # In-memory cache: (from_curr, to_curr, date) -> rate
    _cache: Dict[tuple, Decimal] = {}
    
    @classmethod
    @st.cache_data(ttl=3600)  # Cache for 1 hour
    def get_rate(
        cls,
        from_currency: str,
        to_currency: str,
        target_date: date
    ) -> Decimal:
        """
        Get FX rate for a specific date.
        
        Args:
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency code (e.g., 'EUR')
            target_date: Date for which to get the rate
        
        Returns:
            Exchange rate as Decimal
        """
        # Same currency = 1.0
        if from_currency == to_currency:
            return Decimal(1)
        
        # Check cache
        cache_key = (from_currency, to_currency, target_date)
        if cache_key in cls._cache:
            logger.debug(f"FX rate cache hit: {from_currency}/{to_currency} on {target_date}")
            return cls._cache[cache_key]
        
        # Fetch from yfinance
        try:
            rate = cls._fetch_historical_rate(from_currency, to_currency, target_date)
            cls._cache[cache_key] = rate
            return rate
        except Exception as e:
            logger.warning(f"Could not fetch FX rate for {from_currency}/{to_currency} on {target_date}: {e}")
            # Fallback to current rate
            current_rate = cls._fetch_current_rate(from_currency, to_currency)
            cls._cache[cache_key] = current_rate
            return current_rate
    
    @classmethod
    def _fetch_historical_rate(
        cls,
        from_curr: str,
        to_curr: str,
        target_date: date
    ) -> Decimal:
        """Fetch historical FX rate from yfinance."""
        ticker = f"{from_curr}{to_curr}=X"
        
        # Fetch a week of data around target date to handle weekends/holidays
        start = target_date - timedelta(days=7)
        end = target_date + timedelta(days=1)
        
        logger.info(f"Fetching historical FX rate: {ticker} for {target_date}")
        
        data = yf.download(
            ticker,
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            progress=False
        )
        
        if data.empty:
            raise ValueError(f"No FX data returned for {ticker}")
        
        # Find the closest available date
        data_dates = [d.date() for d in data.index]
        closest_date = min(data_dates, key=lambda d: abs((d - target_date).days))
        
        # Get the close price for that date
        rate = data.loc[data.index[data_dates.index(closest_date)], 'Close']
        
        logger.info(f"FX rate {from_curr}/{to_curr} on {target_date}: {rate:.6f} (from {closest_date})")
        return Decimal(str(rate))
    
    @classmethod
    def _fetch_current_rate(cls, from_curr: str, to_curr: str) -> Decimal:
        """Fetch current FX rate as fallback."""
        ticker = f"{from_curr}{to_curr}=X"
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Try different price fields
            price_fields = ['currentPrice', 'regularMarketPrice', 'previousClose']
            for field in price_fields:
                price = info.get(field)
                if price is not None and price > 0:
                    logger.info(f"Current FX rate {from_curr}/{to_curr}: {price:.6f}")
                    return Decimal(str(price))
            
            # Last resort: try historical 1 day
            hist = stock.history(period='1d')
            if not hist.empty:
                price = hist['Close'].iloc[-1]
                logger.info(f"Current FX rate {from_curr}/{to_curr}: {price:.6f} (from 1d history)")
                return Decimal(str(price))
            
            logger.warning(f"No FX rate found for {from_curr}/{to_curr}, using 1.0")
            return Decimal(1)
            
        except Exception as e:
            logger.error(f"Error fetching current FX rate: {e}")
            return Decimal(1)
    
    @classmethod
    def clear_cache(cls):
        """Clear the FX rate cache (useful for testing)."""
        cls._cache.clear()
        logger.info("FX rate cache cleared")
