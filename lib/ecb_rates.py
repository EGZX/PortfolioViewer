"""
European Central Bank (ECB) FX Rate Provider

Provides official ECB foreign exchange rates for tax compliance.

Features:
- Fetches historical FX rates from ECB API
- Indefinite caching (rates are immutable historical data)
- Used exclusively for tax calculations (legal requiremen

t)
- Fallback to yfinance for non-ECB currencies

API Documentation: https://data.ecb.europa.eu/help/api/data

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import requests
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Dict
import xml.etree.ElementTree as ET

from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


class ECBRateProvider:
    """
    European Central Bank official FX rate provider.
    
    Used for tax-compliant foreign exchange rate lookups.
    Rates are cached indefinitely as they are immutable historical data.
    """
    
    # ECB API endpoint for daily exchange rates
    API_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
    
    # Supported currency codes
    SUPPORTED_CURRENCIES = [
        "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "NZD",
        "SEK", "NOK", "DKK", "PLN", "CZK", "HUF",
        "BGN", "HRK", "RON", "ISK", "TRY",
        "BRL", "CNY", "HKD", "IDR", "INR", "KRW", "MXN", "MYR",
        "PHP", "RUB", "SGD", "THB", "ZAR"
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PortfolioViewer/1.0 (Tax Compliance)",
            "Accept": "application/xml"
        })
    
    def get_rate(
        self,
        target_date: date,
        from_currency: str,
        to_currency: str = "EUR"
    ) -> Optional[Decimal]:
        """
        Get official ECB exchange rate for a specific date.
        
        Args:
            target_date: Date for which to fetch the rate
            from_currency: Source currency code (e.g., 'USD')
            to_currency: Target currency (default: 'EUR')
        
        Returns:
            Exchange rate as Decimal, or None if not available
        
        Notes:
            - Only EUR as target currency is supported (ECB limitation)
            - Rates are published for business days only
            - Will try previous business day if date is weekend/holiday
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        # Validation
        if to_currency != "EUR":
            logger.warning(f"ECB only provides rates to EUR, not {to_currency}")
            return None
        
        if from_currency == "EUR":
            return Decimal("1.0")
        
        if from_currency not in self.SUPPORTED_CURRENCIES:
            logger.warning(f"{from_currency} not supported by ECB")
            return None
        
        # Check cache first
        cached_rate = self._get_cached_rate(target_date, from_currency, to_currency)
        if cached_rate is not None:
            logger.debug(f"ECB rate cache HIT: {from_currency}/EUR on {target_date} = {cached_rate}")
            return Decimal(1) / cached_rate
        
        # Fetch from API
        rate = self._fetch_from_api(target_date, from_currency)
        
        if rate is None:
            # Try previous business day (weekends/holidays)
            for days_back in range(1, 5):
                prev_date = target_date - timedelta(days=days_back)
                rate = self._fetch_from_api(prev_date, from_currency)
                if rate is not None:
                    logger.info(f"ECB rate for {target_date} not available, using {prev_date}: {from_currency}/EUR = {rate}")
                    # Cache with original date for future lookups
                    self._cache_rate(target_date, from_currency, to_currency, rate)
                    return Decimal(1) / rate
        
        if rate is not None:
            # Cache successful fetch
            self._cache_rate(target_date, from_currency, to_currency, rate)
            logger.info(f"ECB rate fetched: {from_currency}/EUR on {target_date} = {rate}")
            return Decimal(1) / rate
        
        logger.warning(f"Could not fetch ECB rate for {from_currency}/EUR on {target_date}")
        return None
    
    def _fetch_from_api(self, target_date: date, currency: str) -> Optional[Decimal]:
        """
        Fetch rate from ECB API for a specific date.
        
        ECB API returns XML in SDMX format.
        """
        try:
            # Format: D.USD.EUR.SP00.A
            url = self.API_URL.format(currency=currency)
            
            # Add date filter as query parameter
            params = {
                "startPeriod": target_date.isoformat(),
                "endPeriod": target_date.isoformat()
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # Find observation value (SDMX Generic format)
            namespaces = {
                'generic': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic',
                'common': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common'
            }
            
            # Look for Obs element with OBS_VALUE
            obs_values = root.findall('.//generic:ObsValue', namespaces)
            if obs_values:
                value_str = obs_values[0].attrib.get('value')
                if value_str:
                    return Decimal(value_str)
            
            # Alternative: Try non-namespaced search
            for obs in root.iter():
                if 'OBS_VALUE' in obs.tag or obs.tag.endswith('ObsValue'):
                    if 'value' in obs.attrib:
                        return Decimal(obs.attrib['value'])
            
            logger.debug(f"No rate found in ECB response for {currency} on {target_date}")
            return None
            
        except requests.RequestException as e:
            logger.error(f"ECB API request failed: {e}")
            return None
        except (ET.ParseError, ValueError) as e:
            logger.error(f"Failed to parse ECB response: {e}")
            return None
    
    def _get_cached_rate(self, target_date: date, from_curr: str, to_curr: str) -> Optional[Decimal]:
        """Get rate from database cache."""
        try:
            from core.db import get_db
            
            db = get_db()
            
            # Ensure fx_rates_ecb table exists
            db.execute_sqlite("""
                CREATE TABLE IF NOT EXISTS fx_rates_ecb (
                    from_curr TEXT NOT NULL,
                    to_curr TEXT NOT NULL,
                    date DATE NOT NULL,
                    rate REAL NOT NULL,
                    source TEXT DEFAULT 'ECB',
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (from_curr, to_curr, date)
                )
            """)
            
            rows = db.query_sqlite(
                "SELECT rate FROM fx_rates_ecb WHERE from_curr = ? AND to_curr = ? AND date = ?",
                (from_curr, to_curr, target_date)
            )
            
            if rows:
                return Decimal(str(rows[0]['rate']))
            
            return None
            
        except Exception as e:
            logger.error(f"Cache lookup failed: {e}")
            return None
    
    def _cache_rate(self, target_date: date, from_curr: str, to_curr: str, rate: Decimal):
        """Store rate in database cache (permanent)."""
        try:
            from core.db import get_db
            
            db = get_db()
            db.execute_sqlite(
                "INSERT OR REPLACE INTO fx_rates_ecb (from_curr, to_curr, date, rate) VALUES (?, ?, ?, ?)",
                (from_curr, to_curr, target_date, float(rate))
            )
            logger.debug(f"Cached ECB rate: {from_curr}/{to_curr} on {target_date} = {rate}")
            
        except Exception as e:
            logger.error(f"Failed to cache rate: {e}")


# Singleton instance
_ecb_provider_instance: Optional[ECBRateProvider] = None


def get_ecb_rate(
    target_date: date,
    from_currency: str,
    to_currency: str = "EUR"
) -> Decimal:
    """
    Get official ECB exchange rate for tax compliance.
    
    This is the REQUIRED function for all tax calculations.
    Do NOT use yfinance rates for tax purposes.
    
    Args:
        target_date: Transaction date
        from_currency: Original transaction currency
        to_currency: Target currency (must be EUR)
    
    Returns:
        Official ECB rate, or fallback rate if ECB unavailable
    
    Example:
        >>> # For a USD transaction on 2024-03-15
        >>> rate = get_ecb_rate(date(2024, 3, 15), "USD", "EUR")
        >>> cost_basis_eur = cost_basis_usd * rate
    """
    global _ecb_provider_instance
    
    if _ecb_provider_instance is None:
        _ecb_provider_instance = ECBRateProvider()
    
    rate = _ecb_provider_instance.get_rate(target_date, from_currency, to_currency)
    
    if rate is None:
        # Fallback: Use yfinance (log warning for compliance)
        logger.warning(
            f"ECB rate not available for {from_currency}/{to_currency} on {target_date}. "
            f"Using yfinance fallback (not tax-compliant)"
        )
        
        from lib.market_data import get_fx_rate
        rate = get_fx_rate(from_currency, to_currency)
    
    return rate


def prefetch_ecb_rates(start_date: date, end_date: date, currencies: list[str]):
    """
    Pre-fetch ECB rates for a date range (optimization).
    
    Use this to batch-load rates before running tax calculations.
    
    Args:
        start_date: Start of date range
        end_date: End of date range
        currencies: List of currency codes to fetch
    """
    global _ecb_provider_instance
    
    if _ecb_provider_instance is None:
        _ecb_provider_instance = ECBRateProvider()
    
    total_days = (end_date - start_date).days + 1
    logger.info(f"Pre-fetching ECB rates for {len(currencies)} currencies over {total_days} days...")
    
    current_date = start_date
    fetched = 0
    
    while current_date <= end_date:
        for currency in currencies:
            if currency != "EUR":
                rate = _ecb_provider_instance.get_rate(current_date, currency, "EUR")
                if rate:
                    fetched += 1
        
        current_date += timedelta(days=1)
    
    logger.info(f"Pre-fetched {fetched} ECB rates")
