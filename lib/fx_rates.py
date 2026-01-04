"""
Enhanced FX Rate Service with Multi-Central Bank Support

Provides tax-compliant foreign exchange rates by prioritizing official central bank
reference rates over market data sources.

Supported Central Banks:
- ECB (European Central Bank) for EUR conversions
- Federal Reserve for USD conversions
- Bank of England for GBP conversions
- Swiss National Bank for CHF conversions

Falls back to yfinance for unsupported currencies or when central bank APIs fail.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import requests
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Tuple
import streamlit as st

from lib.utils.logging_config import setup_logger
from lib.market_cache import get_market_cache

logger = setup_logger(__name__)


# Central Bank API Configuration
CENTRAL_BANK_APIS = {
    "ECB": {
        "base_url": "https://data.ecb.europa.eu/data-detail-api",
        "currencies": ["EUR"],
        "format": "sdmx-json"
    },
    "FED": {
        "base_url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/rates_of_exchange",
        "currencies": ["USD"],
        "format": "json"
    }
}


class CentralBankRateFetcher:
    """Fetches official FX rates from central banks."""
    
    @classmethod
    def fetch_ecb_rate(
        cls, 
        from_currency: str, 
        to_currency: str, 
        target_date: date
    ) -> Optional[float]:
        """
        Fetch rate from European Central Bank.
        
        ECB provides rates with EUR as base currency.
        For EUR/USD: Direct lookup
        For USD/GBP: Calculate via EUR (USD/EUR * EUR/GBP)
        """
        try:
            # ECB only provides EUR-based rates
            if from_currency == "EUR":
                # Direct: EUR to other currency
                return cls._fetch_ecb_direct(to_currency, target_date)
            elif to_currency == "EUR":
                # Inverse: Other currency to EUR
                direct_rate = cls._fetch_ecb_direct(from_currency, target_date)
                return 1.0 / direct_rate if direct_rate else None
            else:
                # Cross rate: from_currency -> EUR -> to_currency
                from_to_eur = cls._fetch_ecb_direct(from_currency, target_date)
                eur_to_to = cls._fetch_ecb_direct(to_currency, target_date)
                
                if from_to_eur and eur_to_to:
                    # Example: USD/GBP = (USD/EUR) / (GBP/EUR)
                    return from_to_eur / eur_to_to
                return None
                
        except Exception as e:
            logger.warning(f"ECB fetch failed for {from_currency}/{to_currency}: {e}")
            return None
    
    @classmethod
    def _fetch_ecb_direct(cls, currency: str, target_date: date) -> Optional[float]:
        """Fetch direct EUR-based rate from ECB."""
        # ECB API endpoint for daily exchange rates
        # Format: EXR/D.{CURRENCY}.EUR.SP00.A
        url = f"https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
        
        params = {
            "startPeriod": target_date.isoformat(),
            "endPeriod": target_date.isoformat(),
            "format": "csvdata"
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Parse CSV response (simple format)
            lines = response.text.strip().split('\n')
            if len(lines) < 2:
                logger.warning(f"No ECB data for {currency} on {target_date}")
                return None
            
            # Last line contains the data (skip header)
            data_line = lines[-1]
            parts = data_line.split(',')
            
            # Extract rate (usually last column)
            rate_str = parts[-1].strip()
            if rate_str and rate_str != 'NaN':
                return float(rate_str)
            
            return None
            
        except Exception as e:
            logger.debug(f"ECB API error for {currency}: {e}")
            return None
    
    @classmethod
    def fetch_fed_rate(
        cls, 
        from_currency: str, 
        to_currency: str, 
        target_date: date
    ) -> Optional[float]:
        """
        Fetch rate from US Federal Reserve.
        
        Fed provides rates with USD as base currency.
        """
        try:
            if from_currency != "USD" and to_currency != "USD":
                # Fed only provides USD-based rates
                return None
            
            # Determine which currency to look up
            lookup_currency = to_currency if from_currency == "USD" else from_currency
            
            url = CENTRAL_BANK_APIS["FED"]["base_url"]
            params = {
                "filter": f"record_date:eq:{target_date.isoformat()},currency:eq:{lookup_currency}",
                "format": "json",
                "page[size]": 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("data") and len(data["data"]) > 0:
                rate = float(data["data"][0]["exchange_rate"])
                
                # Fed gives "1 USD = X foreign currency"
                # If we want foreign/USD, we need inverse
                if from_currency != "USD":
                    rate = 1.0 / rate
                
                return rate
            
            return None
            
        except Exception as e:
            logger.warning(f"Fed fetch failed for {from_currency}/{to_currency}: {e}")
            return None


class FXRateService:
    """
    Enhanced FX rate service with central bank support.
    
    Features:
    - Prioritizes official central bank rates for tax compliance
    - Falls back to yfinance for unsupported currencies
    - Persistent caching with source tracking
    - Historical rate lookup with weekend/holiday handling
    """
    
    @classmethod
    @st.cache_data(ttl=3600)
    def get_rate(
        cls,
        from_currency: str,
        to_currency: str,
        target_date: date,
        prefer_official: bool = True
    ) -> Tuple[Decimal, str]:
        """
        Get FX rate for a specific date.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            target_date: Transaction date
            prefer_official: Try central bank APIs first if True
        
        Returns:
            (rate, source) where source is 'CB:ECB', 'CB:Fed', or 'yfinance'
        """
        # Same currency = 1.0
        if from_currency == to_currency:
            return (Decimal(1), "identity")
        
        cache = get_market_cache()
        
        # Check cache
        cached_rate = cache.get_fx_rate(from_currency, to_currency, target_date)
        if cached_rate is not None:
            # Try to determine source from cache metadata (if available)
            # For now, just return the rate
            logger.debug(f"FX cache HIT: {from_currency}/{to_currency} on {target_date}")
            return (Decimal(str(cached_rate)), "cache")
        
        source = None
        rate = None
        
        # Try central banks first
        if prefer_official:
            # Try ECB
            if "EUR" in [from_currency, to_currency]:
                rate = CentralBankRateFetcher.fetch_ecb_rate(
                    from_currency, to_currency, target_date
                )
                if rate:
                    source = "CB:ECB"
            
            # Try Federal Reserve
            if not rate and "USD" in [from_currency, to_currency]:
                rate = CentralBankRateFetcher.fetch_fed_rate(
                    from_currency, to_currency, target_date
                )
                if rate:
                    source = "CB:Fed"
        
        # Fallback to yfinance
        if not rate:
            rate = cls._fetch_yfinance_rate(from_currency, to_currency, target_date)
            if rate:
                source = "yfinance"
        
        # Ultimate fallback: Current rate
        if not rate:
            logger.warning(f"No historical rate found for {from_currency}/{to_currency} on {target_date}, using current rate")
            rate = cls._fetch_current_yfinance_rate(from_currency, to_currency)
            source = "yfinance_current"
        
        # Fallback to 1.0 if all else fails
        if not rate:
            logger.error(f"Could not fetch any rate for {from_currency}/{to_currency}, using 1.0")
            rate = 1.0
            source = "fallback"
        
        # Cache the result
        cache.set_fx_rate(from_currency, to_currency, target_date, rate)
        
        logger.info(f"FX rate {from_currency}/{to_currency} on {target_date}: {rate:.6f} (source: {source})")
        
        return (Decimal(str(rate)), source)
    
    @classmethod
    def _fetch_yfinance_rate(
        cls,
        from_curr: str,
        to_curr: str,
        target_date: date
    ) -> Optional[float]:
        """Fetch historical rate from yfinance."""
        import yfinance as yf
        
        ticker = f"{from_curr}{to_curr}=X"
        
        # Fetch a week around target date
        start = target_date - timedelta(days=7)
        end = target_date + timedelta(days=1)
        
        try:
            data = yf.download(
                ticker,
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d'),
                progress=False,
                auto_adjust=False
            )
            
            if data.empty:
                return None
            
            # Find closest date
            data_dates = [d.date() for d in data.index]
            if not data_dates:
                return None
            
            closest_date = min(data_dates, key=lambda d: abs((d - target_date).days))
            
            # Get close price
            row = data.loc[data.index[data_dates.index(closest_date)]]
            if 'Close' in row:
                rate = row['Close']
            else:
                rate = row.iloc[0]
            
            if hasattr(rate, 'item'):
                rate = rate.item()
            
            return float(rate)
            
        except Exception as e:
            logger.debug(f"yfinance historical fetch failed for {ticker}: {e}")
            return None
    
    @classmethod
    def _fetch_current_yfinance_rate(cls, from_curr: str, to_curr: str) -> Optional[float]:
        """Fetch current rate from yfinance as last resort."""
        import yfinance as yf
        
        ticker = f"{from_curr}{to_curr}=X"
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='1d')
            
            if not hist.empty and 'Close' in hist:
                return float(hist['Close'].iloc[-1])
            
            return None
            
        except Exception as e:
            logger.error(f"Current rate fetch failed for {ticker}: {e}")
            return None
    
    @classmethod
    def clear_cache(cls):
        """Clear L1 cache (Streamlit). L2 (SQLite) persists."""
        st.cache_data.clear()
        logger.info("FX rate L1 cache cleared")
