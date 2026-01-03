"""
OpenFIGI ISIN to Ticker Resolver

Uses Bloomberg's free OpenFIGI API to resolve ISINs to Yahoo Finance compatible tickers.
Free tier: 25 requests/min, 250 requests/hour (no API key required).
"""

import requests
import time
import re
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


def normalize_ticker(ticker: str) -> str:
    """
    Normalize ticker format for Yahoo Finance compatibility.
    
    Imported from market_data to ensure consistency.
    Converts 'BRK/B' -> 'BRK-B', 'BRK.B' -> 'BRK-B', etc.
    """
    if not ticker:
        return ticker
    
    ticker = ticker.strip().upper()
    
    # Convert slash or period before single letter to hyphen (class shares)
    ticker = re.sub(r'[/\.]([A-Z])$', r'-\1', ticker)
    
    # Handle multi-letter suffixes
    ticker = re.sub(r'/([A-Z]+)$', r'-\1', ticker)
    
    return ticker


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
        from lib.market_cache import get_market_cache
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
                # Cache identity to prevent future lookups
                self.cache_store.set_isin_mapping(isin, isin)
                return isin
            
            # Extract ticker from response
            result = data[0].get('data', [])
            if not result:
                logger.warning(f"OpenFIGI: No data for {isin}")
                return None
            
            # Try to find the best ticker
            ticker = self._extract_best_ticker(result, isin)
            
            if ticker:
                # Normalize ticker before caching
                ticker = normalize_ticker(ticker)
                logger.info(f"✓ Resolved {isin} -> {ticker}")
                self.cache_store.set_isin_mapping(isin, ticker)
                return ticker
            else:
                logger.warning(f"OpenFIGI: Could not extract ticker from response for {isin}")
                # Cache identity
                self.cache_store.set_isin_mapping(isin, isin)
                return isin
                
        except requests.RequestException as e:
            logger.error(f"OpenFIGI API error for {isin}: {e}")
            # Don't cache errors - allow retry next time
            return None
    
    def _extract_best_ticker(self, figi_data: List[Dict], isin: str) -> Optional[str]:
        """
        Extract the best Yahoo Finance ticker, prioritizing Home Markets.
        """
        if not figi_data:
            return None
        
        # 1. robust Exchange Map (MIC Codes -> Yahoo Suffix)
        EXCHANGE_MAP = {
            # US (No suffix)
            'XNYS': '', 'XNAS': '', 'XASE': '', 'ARCX': '', 'BATS': '',
            'US': '',
            
            # DACH Region
            'XETR': '.DE',  # Xetra (Germany)
            'XFRA': '.F',   # Frankfurt
            'XWBO': '.VI',  # Vienna (Austria)
            'XSWX': '.SW',  # SIX Swiss Exchange
            'XVTX': '.SW',  # SIX Swiss (Virt-x)
            
            # Rest of Europe
            'XPAR': '.PA', 'XLON': '.L',  'XAMS': '.AS', 'XBRU': '.BR',
            'XMAD': '.MC', 'XMIL': '.MI', 'XDUB': '.IR', 'XLIS': '.LS',
            'XOSL': '.OL', 'XSTO': '.ST', 'XCSE': '.CO', 'XHEL': '.HE',
            
            # Asia / Pacific
            'XTKS': '.T',  'XHKG': '.HK', 'XASX': '.AX', 'XSES': '.SI',
            
            # Americas
            'XTSE': '.TO', 'XTSX': '.TO', 'XBSP': '.SA',
        }

        # 2. Define "Home Market" map (ISIN Prefix -> Preferred Suffixes)
        HOME_MARKET = {
            'AT': ['.VI'],          # Austria -> Vienna
            'DE': ['.DE', '.F'],    # Germany -> Xetra, Frankfurt
            'FR': ['.PA'],          # France -> Paris
            'GB': ['.L'],           # UK -> London
            'CH': ['.SW'],          # Switzerland -> SIX
            'NL': ['.AS'],          # Netherlands -> Amsterdam
            'IT': ['.MI'],          # Italy -> Milan
            'ES': ['.MC'],          # Spain -> Madrid
            'CA': ['.TO'],          # Canada -> Toronto
            'AU': ['.AX'],          # Australia -> ASX
            'JP': ['.T'],           # Japan -> Tokyo
        }

        country_code = isin[:2]
        preferred_suffixes = HOME_MARKET.get(country_code, [])

        best_ticker = None
        best_score = -1
        
        for item in figi_data:
            ticker = item.get('ticker')
            mic = item.get('exchCode', '') # FIGI uses 'exchCode' which is often the MIC
            security_type = item.get('securityType', '')
            
            if not ticker: continue
            
            score = 0
            
            # Factor 1: Is it a Common Stock?
            if security_type in ['Common Stock', 'Equity']:
                score += 50
            elif security_type == 'ADR':
                score += 10  # ADRs are acceptable but less preferred than primary
            
            # Factor 2: Is it a recognized Yahoo exchange?
            suffix = EXCHANGE_MAP.get(mic)
            if suffix is not None:
                score += 20
                
                # Factor 3: Is it the HOME MARKET? (Crucial for liquidity)
                if suffix in preferred_suffixes:
                    score += 100  # Massive boost for home market listing
                
                # Factor 4: Prefer XETRA over Frankfurt for Germany
                if mic == 'XETR':
                    score += 5
            
            # Factor 5: Composite tickers are usually reliable
            if item.get('compositeFIGI'):
                score += 10

            # Selection
            if score > best_score:
                best_score = score
                if suffix is not None:
                    best_ticker = f"{ticker}{suffix}"
                else:
                    # Fallback for US or unknown exchanges
                    best_ticker = ticker
        
        # Normalize before returning
        if best_ticker:
            best_ticker = normalize_ticker(best_ticker)
        
        return best_ticker
    
    def resolve_batch(self, isins: List[str]) -> Dict[str, Optional[str]]:
        """
        Resolve multiple ISINs in batch using OpenFIGI's batch API.
        Checks cache first, then fetches missing ISINs in chunks of 100.
        """
        results = {}
        to_fetch = []
        
        # 1. Check Cache
        for isin in isins:
            cached = self.cache_store.get_isin_mapping(isin)
            if cached:
                results[isin] = cached
            elif isin and len(isin) == 12: # Only valid ISINs
                to_fetch.append(isin)
            else:
                results[isin] = None # Invalid, don't try
        
        if not to_fetch:
            return results
            
        logger.info(f"OpenFIGI Batch: {len(results)} cached, {len(to_fetch)} to resolve")
        
        # 2. Chunk into groups of 10 (OpenFIGI limit)
        CHUNK_SIZE = 10
        for i in range(0, len(to_fetch), CHUNK_SIZE):
            chunk = to_fetch[i:i + CHUNK_SIZE]
            
            # Rate limit
            self._rate_limit()
            
            # Prepare payload
            payload = [{"idType": "ID_ISIN", "idValue": isin} for isin in chunk]
            
            try:
                logger.info(f"Fetching OpenFIGI batch {i//CHUNK_SIZE + 1} ({len(chunk)} items)...")
                response = requests.post(
                    self.API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30 # Increased timeout for batch
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # OpenFIGI returns array of results corresponding to the input array
                    # Each item is either {data: [...]} or {error: ...}
                    for idx, item_result in enumerate(data):
                        original_isin = chunk[idx]
                        
                        if 'data' in item_result:
                            # Extract best ticker
                            ticker = self._extract_best_ticker(item_result['data'], original_isin)
                            if ticker:
                                # Normalize before caching and returning
                                ticker = normalize_ticker(ticker)
                                results[original_isin] = ticker
                                self.cache_store.set_isin_mapping(original_isin, ticker)
                                logger.debug(f"Resolved {original_isin} -> {ticker}")
                            else:
                                results[original_isin] = None
                                logger.warning(f"No suitable ticker parsing for {original_isin}")
                        else:
                            # Error or not found - Cache as identity to prevent retry
                            results[original_isin] = original_isin
                            # Store in DB so we don't ask OpenFIGI again for this ISIN
                            self.cache_store.set_isin_mapping(original_isin, original_isin)
                            logger.info(f"OpenFIGI: No match for {original_isin}, cached as identity.")
                            
                else:
                    logger.error(f"OpenFIGI batch failed: {response.status_code} - {response.text}")
                    # Mark all this chunks as failed
                    for isin in chunk:
                        results[isin] = None
                        
            except Exception as e:
                logger.error(f"OpenFIGI batch exception: {e}")
                for isin in chunk:
                    results[isin] = None
            
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
