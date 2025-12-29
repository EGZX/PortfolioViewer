"""
ISIN to Yahoo Finance Ticker Resolver

Provides intelligent ISIN-to-ticker mapping for European and US securities.
"""

import re
from typing import Optional, Dict
from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class ISINResolver:
    """Resolves ISINs to Yahoo Finance ticker symbols."""
    
    # Known ISIN patterns for different exchanges
    EXCHANGE_PATTERNS = {
        'DE': '.DE',  # German stocks (Xetra)
        'FR': '.PA',  # French stocks (Paris)
        'GB': '.L',   # UK stocks (London)
        'IT': '.MI',  # Italian stocks (Milan)
        'ES': '.MC',  # Spanish stocks (Madrid)
        'NL': '.AS',  # Dutch stocks (Amsterdam)
        'CH': '.SW',  # Swiss stocks (SIX Swiss Exchange)
        'US': '',     # US stocks (no suffix needed)
    }
    
    @classmethod
    def resolve_isin(cls, isin: str, fallback_ticker: Optional[str] = None) -> str:
        """
        Attempt to resolve ISIN to Yahoo Finance ticker.
        
        Resolution strategy:
        1. Check manual TICKER_OVERRIDES (in market_data.py) - highest priority
        2. Try OpenFIGI API for automatic resolution
        3. Use provided fallback_ticker
        4. Return ISIN as-is (will use last transaction price)
        
        Args:
            isin: ISIN code (e.g., 'DE000BASF111')
            fallback_ticker: Fallback ticker if ISIN can't be resolved
        
        Returns:
            Yahoo Finance ticker symbol
        """
        if not isin or len(isin) != 12:
            return fallback_ticker or isin
        
        # Check if there's a manual override in market_data.py
        # (imported here to avoid circular dependency)
        try:
            from services.market_data import TICKER_OVERRIDES
            if isin in TICKER_OVERRIDES:
                override = TICKER_OVERRIDES[isin]
                logger.info(f"Using manual override for {isin}: {override}")
                return override
        except ImportError:
            pass
        
        # If we have a fallback ticker explicitly provided, use it
        if fallback_ticker:
            logger.info(f"Using provided ticker for {isin}: {fallback_ticker}")
            return fallback_ticker
        
        # Try OpenFIGI automatic resolution
        try:
            from services.openfigi_resolver import get_openfigi_resolver
            resolver = get_openfigi_resolver()
            ticker = resolver.resolve_isin(isin)
            
            if ticker:
                logger.info(f"OpenFIGI resolved {isin} -> {ticker}")
                return ticker
        except Exception as e:
            logger.warning(f"OpenFIGI resolution failed for {isin}: {e}")
        
        # Last resort: return ISIN as-is
        # Portfolio will use last transaction price as fallback
        logger.debug(f"Could not resolve {isin}, returning as-is. Add to TICKER_OVERRIDES for manual mapping.")
        return isin
    
    @classmethod
    def needs_resolution(cls, identifier: str) -> bool:
        """Check if identifier is an ISIN that needs resolution."""
        # ISIN format: 2-letter country code + 9 alphanumeric + 1 check digit
        if not identifier or len(identifier) != 12:
            return False
        
        # Check if it matches ISIN pattern
        return bool(re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', identifier))
