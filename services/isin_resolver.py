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
        
        Args:
            isin: ISIN code (e.g., 'DE000BASF111')
            fallback_ticker: Fallback ticker if ISIN can't be resolved
        
        Returns:
            Yahoo Finance ticker symbol (may still be ISIN if unresolvable)
        """
        if not isin or len(isin) != 12:
            return fallback_ticker or isin
        
        # Extract country code (first 2 characters)
        country_code = isin[:2]
        
        # For European stocks, try to construct ticker from ISIN
        if country_code in cls.EXCHANGE_PATTERNS:
            exchange_suffix = cls.EXCHANGE_PATTERNS[country_code]
            
            # Extract numeric/alpha part and construct ticker
            # This is a heuristic - may not always work
            # For German stocks: DE000BASF111 -> try BASF.DE
            # Extract the company identifier (usually characters 5-9)
            company_part = isin[5:9].rstrip('0')
            
            if company_part:
                ticker = f"{company_part}{exchange_suffix}"
                logger.info(f"Resolved ISIN {isin} -> {ticker} (heuristic)")
                return ticker
        
        # If we have a fallback, use it
        if fallback_ticker:
            logger.info(f"Using fallback ticker for {isin}: {fallback_ticker}")
            return fallback_ticker
        
        # Last resort: return ISIN itself (will likely fail price fetch)
        logger.warning(f"Could not resolve ISIN {isin}, using as ticker")
        return isin
    
    @classmethod
    def needs_resolution(cls, identifier: str) -> bool:
        """Check if identifier is an ISIN that needs resolution."""
        # ISIN format: 2-letter country code + 9 alphanumeric + 1 check digit
        if not identifier or len(identifier) != 12:
            return False
        
        # Check if it matches ISIN pattern
        return bool(re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', identifier))
