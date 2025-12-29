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
from services.market_cache import get_market_cache

logger = setup_logger(__name__)


class FXRateService:
    """
    Manages historical FX rate lookup and caching.
    
    Features:
    - Persistent caching via MarketDataCache (SQLite)
    - Fallback to current rates when historical unavailable
    - Support for all major currency pairs via yfinance
    """
    
    @classmethod
    @st.cache_data(ttl=3600)  # L1 Cache: Memory (1 hour)
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
            
        cache = get_market_cache()
        
        # L2 Cache: Check SQLite
        cached_rate = cache.get_fx_rate(from_currency, to_currency, target_date)
        if cached_rate is not None:
            logger.debug(f"FX cache HIT: {from_currency}/{to_currency} on {target_date} = {cached_rate}")
            return Decimal(str(cached_rate))
        
        # Fetch from yfinance
        try:
            rate = cls._fetch_historical_rate(from_currency, to_currency, target_date)
            # Save to L2 Cache
            cache.set_fx_rate(from_currency, to_currency, target_date, float(rate))
            return rate
        except Exception as e:
            logger.warning(f"Could not fetch FX rate for {from_currency}/{to_currency} on {target_date}: {e}")
            # Fallback to current rate
            current_rate = cls._fetch_current_rate(from_currency, to_currency)
            # Don't cache fallback permanently for a specific historical date (it's inaccurate)
            # Or maybe we should? For now, we return it but don't pollute the historical cache.
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
        
        # Use existing market data service or direct yf? Direct yf is isolated here.
        # Ensure thread safety/rate limits if relevant, but yf is usually fine.
        data = yf.download(
            ticker,
            start=start.strftime('%Y-%m-%d'),
            end=end.strftime('%Y-%m-%d'),
            progress=False,
            auto_adjust=False # Important for FX? usually actions don't apply, but good practice
        )
        
        if data.empty:
            raise ValueError(f"No FX data returned for {ticker}")
        
        # Find the closest available date
        # data.index contains dates.
        data_dates = [d.date() for d in data.index]
        if not data_dates:
             raise ValueError(f"No FX data dates returned for {ticker}")
             
        closest_date = min(data_dates, key=lambda d: abs((d - target_date).days))
        
        # Check if closest date is too far (e.g. > 10 days), might be irrelevant data
        if abs((closest_date - target_date).days) > 10:
             logger.warning(f"Closest FX date {closest_date} is far from target {target_date}")

        # Get the close price for that date
        # Handle MultiIndex columns if yfinance returns them (it sometimes does)
        try:
            row = data.loc[data.index[data_dates.index(closest_date)]]
            if 'Close' in row:
                rate = row['Close']
            else:
                rate = row.iloc[0] # Fallback
        except Exception as e:
            # Fallback for complex df structures
            rate = data['Close'].iloc[-1]
        
        # Ensure scalar
        if hasattr(rate, 'item'):
            rate = rate.item()
            
        logger.info(f"FX rate {from_curr}/{to_curr} on {target_date}: {rate:.6f} (from {closest_date})")
        return Decimal(str(rate))
    
    @classmethod
    def _fetch_current_rate(cls, from_curr: str, to_curr: str) -> Decimal:
        """Fetch current FX rate as fallback."""
        ticker = f"{from_curr}{to_curr}=X"
        
        try:
            stock = yf.Ticker(ticker)
            # Fast track: info is often slow. try history 1d directly.
            hist = stock.history(period='1d')
            if not hist.empty and 'Close' in hist:
                price = hist['Close'].iloc[-1]
                logger.info(f"Current FX rate {from_curr}/{to_curr}: {price:.6f} (from 1d history)")
                return Decimal(str(price))
            
            # Fallback to info
            info = stock.info
            price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
            
            if price is not None and price > 0:
                return Decimal(str(price))
            
            logger.warning(f"No FX rate found for {from_curr}/{to_curr}, using 1.0")
            return Decimal(1)
            
        except Exception as e:
            logger.error(f"Error fetching current FX rate: {e}")
            return Decimal(1)
    
    @classmethod
    def clear_cache(cls):
        """Clear the L1 cache (Streamlit). L2 is persistent."""
        st.cache_data.clear()
        logger.info("FX rate L1 cache cleared")
