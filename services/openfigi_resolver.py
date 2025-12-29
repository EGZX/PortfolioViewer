"""
OpenFIGI ISIN to Ticker Resolver

Uses Bloomberg's free OpenFIGI API to resolve ISINs to Yahoo Finance compatible tickers.
Free tier: 25 requests/min, 250 requests/hour (no API key required).
"""

import requests
import time
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class OpenFIGIResolver:
    """
    Resolve ISINs to Yahoo Finance tickers using OpenFIGI API.
    
    Caches successful resolutions in memory to avoid repeated API calls.
    """
    
    API_URL = "https://api.openfigi.com/v3/mapping"
    RATE_LIMIT_DELAY = 2.5  # Seconds between requests (24 req/min = safe margin)
    
    def __init__(self):
        self.last_request_time: Optional[datetime] = None
        # Use MarketDataCache for persistent storage
        from services.market_cache import get_market_cache
        self.cache_store = get_market_cache()
    
    def _rate_limit(self):
        """Enforce rate limiting to stay within free tier limits."""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < self.RATE_LIMIT_DELAY:
                sleep_time = self.RATE_LIMIT_DELAY - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
        self.last_request_time = datetime.now()
    
    def resolve_isin(self, isin: str) -> Optional[str]:
        """
        Resolve a single ISIN to Yahoo Finance ticker.
        
        Args:
            isin: ISIN code (e.g., 'US0378331005')
        
        Returns:
            Yahoo Finance ticker symbol or None if not found
        """
        # Check cache first
        cached_ticker = self.cache_store.get_isin_mapping(isin)
        if cached_ticker:
            logger.debug(f"Cache HIT: {isin} -> {cached_ticker}")
            return cached_ticker
        
        # Validate ISIN format
        if not isin or len(isin) != 12:
            logger.warning(f"Invalid ISIN format: {isin}")
            return None
        
        logger.info(f"Resolving ISIN via OpenFIGI: {isin}")
        
        # Rate limit
        self._rate_limit()
        
        # Prepare request
        payload = [{
            "idType": "ID_ISIN",
            "idValue": isin,
            "exchCode": "US"  # Prefer US exchanges for Yahoo Finance compatibility
        }]
        
        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            if not data or 'error' in data[0]:
                logger.warning(f"OpenFIGI: No mapping found for {isin}")
                # We could cache "not found" (e.g. empty string or special value) 
                # but MarketDataCache logic for None is tricky. For now, don't cache failures.
                return None
            
            # Extract ticker from response
            result = data[0].get('data', [])
            if not result:
                logger.warning(f"OpenFIGI: No data for {isin}")
                return None
            
            # Try to find the best ticker
            ticker = self._extract_best_ticker(result, isin)
            
            if ticker:
                logger.info(f"✓ Resolved {isin} -> {ticker}")
                self.cache_store.set_isin_mapping(isin, ticker)
                return ticker
            else:
                logger.warning(f"OpenFIGI: Could not extract ticker from response for {isin}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"OpenFIGI API error for {isin}: {e}")
            # Don't cache errors - allow retry next time
            return None
    
    def _extract_best_ticker(self, figi_data: List[Dict], isin: str) -> Optional[str]:
        """
        Extract the best Yahoo Finance compatible ticker from OpenFIGI response.
        
        Prioritizes:
        1. Composite tickers (most liquid)
        2. Primary exchange listings
        3. US exchanges (best Yahoo Finance coverage)
        """
        if not figi_data:
            return None
        
        # Get country code from ISIN
        country_code = isin[:2]
        
        # Mapping of common exchanges to Yahoo Finance suffixes
        EXCHANGE_SUFFIXES = {
            'US': '',          # US stocks have no suffix
            'XNYS': '',        # NYSE
            'XNAS': '',        # NASDAQ
            'XLON': '.L',      # London
            'XPAR': '.PA',     # Paris
            'XFRA': '.DE',     # Frankfurt
            'XETRA': '.DE',    # XETRA (German)
            'XSWX': '.SW',     # Swiss
            'XTSE': '.TO',     # Toronto
            'XHKG': '.HK',     # Hong Kong
            'XTKS': '.T',      # Tokyo
            'XASX': '.AX',     # Australia
        }
        
        best_ticker = None
        best_score = -1
        
        for item in figi_data:
            ticker = item.get('ticker')
            exchange = item.get('exchCode', '')
            security_type = item.get('securityType', '')
            
            if not ticker:
                continue
            
            # Score this result
            score = 0
            
            # Prefer composite tickers (most liquid)
            if item.get('compositeFIGI'):
                score += 10
            
            # Prefer common shares
            if security_type in ['Common Stock', 'Equity', 'ADR']:
                score += 5
            
            # Prefer recognized exchanges
            if exchange in EXCHANGE_SUFFIXES:
                score += 3
            
            # Check if this is better than what we have
            if score > best_score:
                best_score = score
                
                # Format ticker for Yahoo Finance
                suffix = EXCHANGE_SUFFIXES.get(exchange, '')
                best_ticker = f"{ticker}{suffix}"
        
        return best_ticker
    
    def resolve_batch(self, isins: List[str]) -> Dict[str, Optional[str]]:
        """
        Resolve multiple ISINs in batch.
        
        Note: OpenFIGI supports batch requests, but we process one at a time
        to stay well within rate limits and handle errors gracefully.
        
        Args:
            isins: List of ISIN codes
        
        Returns:
            Dictionary mapping ISIN -> Ticker (or None)
        """
        results = {}
        
        for isin in isins:
            ticker = self.resolve_isin(isin)
            results[isin] = ticker
        
        return results
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cached resolutions from DB."""
        # This is a bit expensive for a stats call, so we'll simplify or remove it
        # Rely on market_cache stats
        return self.cache_store.get_stats()


# Global singleton instance
_resolver_instance: Optional[OpenFIGIResolver] = None


def get_openfigi_resolver() -> OpenFIGIResolver:
    """Get or create global OpenFIGI resolver instance."""
    global _resolver_instance
    
    if _resolver_instance is None:
        _resolver_instance = OpenFIGIResolver()
    
    return _resolver_instance
