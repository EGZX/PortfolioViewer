"""
ISIN to Yahoo Finance Ticker Resolver

Provides intelligent ISIN-to-ticker mapping for European and US securities.
"""

import re
from typing import Optional, Dict
from lib.utils.logging_config import setup_logger

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
    
    # Manual overrides for specific ISINs that yfinance or OpenFIGI struggle with
    # This replaces the need for circular imports from market_data
    TICKER_OVERRIDES = {
        # US ADRs - yfinance works better with ticker symbols than ISINs
        'US8740391003': 'TSM',  # Taiwan Semiconductor ADR
        'US02079K3059': 'GOOGL',  # Alphabet Class A
        'US0404131064': 'ARKK',  # ARK Innovation ETF
        
        # Asian stocks
        'CNE100000296': '1211.HK',  # BYD Company (Hong Kong)
        
        # European ETFs - add .L suffix for London listing or use local ticker
        'IE000716YHJ7': 'FWRA.MI',  # Invesco FTSE All-World UCITS ETF (Milan - EUR)
        'AT0000A0E9W5': 'SPIW.DE',  # Example
        'IE00B3RBWM25': 'VWRL.AS',  # Vanguard FTSE All-World (Amsterdam)
        'US64110L1061': 'NFLX',     # Netflix
        'DE000A0HHJR3': 'CLIQ.DE',  # Cliq Digital
        
        # Previously failing stocks (from user screenshot)
        # Previously failing stocks
        'PLDNPLU00011': 'DNP.WA',    # Dino Polska (Warsaw - PLN)
        'NL0010273215': 'ASML.AS',   # ASML Holding (Amsterdam - EUR)
        'LU1176118681': 'EQT.ST',    # EQT AB (Stockholm - SEK)
        'DK0010272202': 'GMAB.CO',   # Genmab (Copenhagen - DKK)
        'US60733R1023': 'NATKY',     # NAC Kazatomprom GDR (US OTC)
        'NL9005294274': 'ENX.PA',    # Euronext NV (Paris)
        'US45841N1072': 'IBKR',      # Interactive Brokers (Explicit)
        
        # Crypto
        'BTC': 'BTC-EUR',
        'ETH': 'ETH-EUR',
        'SOL': 'SOL-EUR',
    }
    
    @classmethod
    def resolve_isin(cls, isin: str, fallback_ticker: Optional[str] = None) -> str:
        """
        Attempt to resolve ISIN to Yahoo Finance ticker.
        
        Resolution strategy:
        1. Check manual TICKER_OVERRIDES - highest priority
        2. Try OpenFIGI API for automatic resolution
        3. Use provided fallback_ticker
        4. Return ISIN as-is (will use last transaction price)
        """
        if not isin:
            return fallback_ticker or ""
            
        # Check manual overrides first
        # This works for both ISINs and other identifiers (e.g. BTC)
        if isin in cls.TICKER_OVERRIDES:
            override = cls.TICKER_OVERRIDES[isin]
            logger.info(f"Using manual override for {isin}: {override}")
            return override
        
        # If not an ISIN (length 12), return as is (unless overridden above)
        if len(isin) != 12:
             return fallback_ticker or isin
        
        # If we have a fallback ticker explicitly provided, use it
        if fallback_ticker:
            logger.info(f"Using provided ticker for {isin}: {fallback_ticker}")
            return fallback_ticker
        
        # Try OpenFIGI automatic resolution
        try:
            from lib.openfigi_resolver import get_openfigi_resolver
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
    def resolve_batch(cls, tickers: list[str]) -> Dict[str, str]:
        """
        Resolve a batch of tickers/ISINs.
        Returns map of {original_ticker: resolved_ticker}.
        """
        results = {}
        isins_to_resolve = []
        
        # 1. Check overrides and simple cases
        for t in tickers:
            if not t:
                continue
                
            if t in cls.TICKER_OVERRIDES:
                results[t] = cls.TICKER_OVERRIDES[t]
            elif len(t) == 12 and re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', t):
                # Is likely an ISIN, needs OpenFIGI
                isins_to_resolve.append(t)
            else:
                # Not an ISIN, assume it's already a ticker
                results[t] = t
                
        # 2. Batch resolve ISINs
        if isins_to_resolve:
            try:
                from lib.openfigi_resolver import get_openfigi_resolver
                resolver = get_openfigi_resolver()
                
                # This uses the optimized batch method we just added
                batch_results = resolver.resolve_batch(isins_to_resolve)
                
                for isin, resolved in batch_results.items():
                    if resolved:
                        results[isin] = resolved
                    else:
                        results[isin] = isin # Fallback to original
                        
            except Exception as e:
                logger.error(f"Batch resolution failed: {e}")
                for isin in isins_to_resolve:
                    results[isin] = isin
                    
        return results

    @classmethod
    def needs_resolution(cls, identifier: str) -> bool:
        """Check if identifier is an ISIN or overridden ticker that needs resolution."""
        if not identifier:
            return False
            
        # Check overrides first (allows remapping non-ISINs like BTC)
        if identifier in cls.TICKER_OVERRIDES:
            return True
            
        # ISIN format: 2-letter country code + 9 alphanumeric + 1 check digit
        if len(identifier) != 12:
            return False
        
        # Check if it matches ISIN pattern
        return bool(re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', identifier))
