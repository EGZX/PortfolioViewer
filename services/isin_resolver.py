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
        
        NOTE: The heuristic resolution has been disabled as it was creating
        invalid tickers. ISINs are now returned as-is, which will cause price
        fetch to fail, but the portfolio will use last transaction price as
        fallback (which is more accurate than invalid/delisted ticker prices).
        
        Args:
            isin: ISIN code (e.g., 'DE000BASF111')
            fallback_ticker: Fallback ticker if ISIN can't be resolved
        
        Returns:
            Yahoo Finance ticker symbol (will be ISIN if unresolvable)
        """
        if not isin or len(isin) != 12:
            return fallback_ticker or isin
        
        # If we have a fallback ticker explicitly provided, use it
        if fallback_ticker:
            logger.info(f"Using provided ticker for {isin}: {fallback_ticker}")
            return fallback_ticker
        
        # Heuristic resolution is disabled - it was creating invalid tickers
        # like "0001", "53R2", etc. that don't exist on Yahoo Finance
        # 
        # Return ISIN as-is. Yahoo Finance will fail to fetch price, but
        # portfolio valuation will use last transaction price as fallback,
        # which is more accurate than using a wrong/delisted ticker's price.
        logger.debug(f"Returning ISIN as ticker: {isin} (use TICKER_OVERRIDES in market_data.py for known mappings)")
        return isin
    
    @classmethod
    def needs_resolution(cls, identifier: str) -> bool:
        """Check if identifier is an ISIN that needs resolution."""
        # ISIN format: 2-letter country code + 9 alphanumeric + 1 check digit
        if not identifier or len(identifier) != 12:
            return False
        
        # Check if it matches ISIN pattern
        return bool(re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', identifier))
