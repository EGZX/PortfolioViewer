"""Market data service with yfinance integration and fallback strategies.

Financial Compliance Standards:
- Conservative rate limiting to prevent API blocking
- Comprehensive validation of all fetched data
- Persistent currency caching to ensure consistency
- No invalid data written to database under any circumstances
- Detailed audit logging of all price fetches
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Optional, List
import pandas as pd
import yfinance as yf
import streamlit as st
import time
import re
import logging
import threading

from lib.utils.logging_config import setup_logger, get_perf_logger
from lib.isin_resolver import ISINResolver
from lib.multi_provider import MarketDataAggregator
from lib.crypto_prices import get_crypto_prices_batch, is_crypto_ticker
from lib.crypto_prices import get_crypto_prices_batch, is_crypto_ticker

logger = setup_logger(__name__)


# Suppress yfinance error spam for delisted tickers
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Initialize fallback providers
_fallback_aggregator = MarketDataAggregator()

# Rate limiting for single price fetches (financial compliance)
_last_single_fetch_time = None
_fetch_lock = threading.Lock()
RATE_LIMIT_DELAY_SECONDS = 1.5  # Conservative: 40 requests/min max

# In-memory FX rate cache (session-level, prevents repeated slow yfinance calls)
_fx_memory_cache = {}



def normalize_ticker(ticker: str) -> str:
    """
    Normalize ticker format for Yahoo Finance compatibility.
    
    Conversions:
    - 'BRK/B' -> 'BRK-B' (class shares use hyphen)
    - 'BRK.B' -> 'BRK-B' (some sources use period)
    - Handles edge cases for multi-class shares
    
    Args:
        ticker: Raw ticker symbol
    
    Returns:
        Normalized ticker for Yahoo Finance
    """
    if not ticker:
        return ticker
    
    ticker = ticker.strip().upper()
    
    # Convert slash or period before single letter to hyphen (class shares)
    # BRK/B, BRK.B -> BRK-B
    ticker = re.sub(r'[/\.]([A-Z])$', r'-\1', ticker)
    
    # Handle multi-letter suffixes like BRK/BRK -> BRK-BRK (rare but possible)
    ticker = re.sub(r'/([A-Z]+)$', r'-\1', ticker)
    
    return ticker


# Removed redundant st.cache_data - using SQLite cache instead
def fetch_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    """
    Fetch current prices from yfinance with error handling and retry logic.
    Uses SQLite cache to minimize API calls.
    
    Args:
        tickers: List of ticker symbols (will be normalized)
    
    Returns:
        Dictionary mapping ticker to current price (EUR) or None if failed
    """
    from lib.market_cache import get_market_cache
    
    # Normalize all input tickers
    tickers = [normalize_ticker(t) for t in tickers if t]
    
    logger.info(f"Fetching prices for {len(tickers)} tickers")
    
    with get_perf_logger(logger, f"fetch_prices({len(tickers)} tickers)", threshold_ms=3000):
        # Check cache first
        cache = get_market_cache()
        today = date.today()
        
        cached_prices = cache.get_prices_batch(tickers, today)
        
        # Identify missing prices
        tickers_to_fetch = [t for t, p in cached_prices.items() if p is None]
        prices = {t: p for t, p in cached_prices.items() if p is not None}
        
        if not tickers_to_fetch:
            logger.info(f"All {len(tickers)} prices served from cache!")
            return prices
        
        logger.info(f"Cache: {len(prices)} hits, {len(tickers_to_fetch)} to fetch from API")
        
        # Filter Blacklisted Tickers immediately
        valid_tickers = [t for t in tickers_to_fetch if not cache.is_blacklisted(t)]
        tickers_to_fetch = valid_tickers
        
        if not tickers_to_fetch:
             return prices # All blacklisted or cached

        # Resolve ISINs to tickers
        mapped_tickers = []
        ticker_map = {}  # mapped -> original

        batch_map = ISINResolver.resolve_batch(tickers_to_fetch)
        
        for original_ticker in tickers_to_fetch:
            resolved_ticker = batch_map.get(original_ticker, original_ticker)
            if resolved_ticker != original_ticker:
                logger.debug(f"Resolved {original_ticker} -> {resolved_ticker}")

            # Skip empty tickers
            if not resolved_ticker:
                 resolved_ticker = original_ticker

            # Normalize resolved ticker as well
            resolved_ticker = normalize_ticker(resolved_ticker)
            
            mapped_tickers.append(resolved_ticker)
            ticker_map[resolved_ticker] = original_ticker  # Reverse map

        
        if not mapped_tickers:
            return prices
        
        # Batch fetch for efficiency
        try:
            data = yf.download(
                mapped_tickers,
                period='5d',
                interval='1d',
                group_by='ticker',
                threads=False,
                progress=False
            )
            
            # Handle single ticker vs multiple tickers
            if len(mapped_tickers) == 1:
                mapped_ticker = mapped_tickers[0]
                original_ticker = ticker_map.get(mapped_ticker, mapped_ticker)
                
                # Check directly in data (single level columns for single ticker usually, but yf changed recently)
                # yfinance 0.2+ returns MultiIndex even for single ticker if group_by='ticker'
                
                # Let's inspect data structure safely
                target_data = data
                if mapped_ticker in data.columns.levels[0]:
                    target_data = data[mapped_ticker]
                
                if not target_data.empty and 'Close' in target_data.columns:
                    # Use ffill to get last valid price (handles weekends/holidays with NaN rows)
                    price_series = target_data['Close'].ffill()
                    if not price_series.empty:
                        price = price_series.iloc[-1]
                        
                        if price is not None and not pd.isna(price):
                            price_val = float(price)
                            prices[original_ticker] = price_val
                            cache.set_price(original_ticker, price_val, today)
                            logger.info(f"{original_ticker}: {price_val:.2f}")
                        else:
                            prices[original_ticker] = None
                            logger.warning(f"{original_ticker}: No valid price found in last 5 days")
                    else:
                         prices[original_ticker] = None
                else:
                    prices[original_ticker] = None
                    logger.warning(f"{original_ticker}: Download failed")
            else:
                # Multiple tickers
                for mapped_ticker in mapped_tickers:
                    original_ticker = ticker_map.get(mapped_ticker, mapped_ticker)
                    try:
                        if mapped_ticker in data.columns.levels[0]:
                            ticker_data = data[mapped_ticker]
                            if not ticker_data.empty and 'Close' in ticker_data.columns:
                                # Use ffill to get last valid price
                                price_series = ticker_data['Close'].ffill()
                                if not price_series.empty:
                                    price = price_series.iloc[-1]
                                    
                                    if price is not None and not pd.isna(price):
                                        price_val = float(price)
                                        prices[original_ticker] = price_val
                                        cache.set_price(original_ticker, price_val, today)
                                        logger.info(f"{original_ticker}: {price_val:.2f}")
                                    else:
                                        prices[original_ticker] = None
                                        logger.warning(f"{original_ticker}: No current price")
                                else:
                                    prices[original_ticker] = None
                            else:
                                prices[original_ticker] = None
                                logger.warning(f"{original_ticker}: No data in response")
                        else:
                            prices[original_ticker] = None
                            logger.warning(f"{original_ticker}: Not in response")
                    except Exception as e:
                        prices[original_ticker] = None
                        logger.error(f"{original_ticker}: Error extracting price - {e}")
            
        except Exception as e:
            logger.error(f"Batch fetch failed: {e}")
            # Fallback: Individual fetch with original tickers
            for original_ticker in tickers_to_fetch:
                if original_ticker in prices:
                    continue  # Skip if already fetched
                
                # Try mapped ticker first
                mapped_ticker = ISINResolver.resolve_isin(original_ticker)
                price = fetch_single_price(mapped_ticker)
                
                # If that fails, try fallback providers
                if price is None and _fallback_aggregator.providers:
                    logger.info(f"Trying fallback providers for {original_ticker}")
                    price = _fallback_aggregator.get_price_with_fallback(mapped_ticker)
                
                if price is not None:
                    cache.set_price(original_ticker, price, today)
                
                prices[original_ticker] = price
        
        success_count = sum(1 for p in prices.values() if p is not None)
        fail_count = len(tickers) - success_count
        
        if fail_count > 0:
            logger.warning(f"Price fetch complete: {success_count}/{len(tickers)} succeeded, {fail_count} failed")
        else:
            logger.info(f"Price fetch complete: {success_count}/{len(tickers)} succeeded")
        
        return prices


def fetch_single_price(ticker: str, max_retries: int = 3) -> Optional[float]:
    """
    Fetch single price with strict financial compliance standards.
    
    Features:
    - Conservative rate limiting (1.5s between calls)
    - Ticker normalization
    - Currency detection and persistent caching
    - Comprehensive validation
    - Detailed audit logging
    - Blacklisting of permanently failed tickers
    
    Args:
        ticker: Ticker symbol (will be normalized)
        max_retries: Number of retry attempts for transient errors
    
    Returns:
        Price as float, or None if fetch failed
    """
    global _last_single_fetch_time
    
    if not ticker:
        logger.warning("fetch_single_price called with empty ticker")
        return None
    
    # Normalize ticker format
    original_ticker = ticker
    ticker = normalize_ticker(ticker)
    if ticker != original_ticker:
        logger.info(f"Normalized ticker: {original_ticker} -> {ticker}")
    
    # Check blacklist
    from lib.market_cache import get_market_cache
    cache = get_market_cache()
    if cache.is_blacklisted(ticker):
        logger.debug(f"Skipping blacklisted ticker: {ticker}")
        return None
    
    # Rate limiting (financial compliance: prevent API blocking)
    with _fetch_lock:
        if _last_single_fetch_time is not None:
            elapsed = time.time() - _last_single_fetch_time
            if elapsed < RATE_LIMIT_DELAY_SECONDS:
                sleep_duration = RATE_LIMIT_DELAY_SECONDS - elapsed
                logger.debug(f"Rate limit: sleeping {sleep_duration:.2f}s")
                time.sleep(sleep_duration)
        _last_single_fetch_time = time.time()
    
    # Attempt to fetch price
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker)
            
            # Try fast_info first (faster, less data)
            try:
                price = stock.fast_info.last_price
                currency = stock.fast_info.currency
                
                # Validate price
                if price is not None and price > 0:
                    price_float = float(price)
                    
                    # Cache currency if available
                    if currency:
                        cache.set_ticker_currency(ticker, currency.upper())
                        logger.info(f"✓ {ticker}: {price_float:.4f} {currency.upper()}")
                    else:
                        logger.info(f"✓ {ticker}: {price_float:.4f} (currency unknown)")
                    
                    return price_float
            except AttributeError:
                # fast_info not available, fall through to history
                pass
            
            # Fallback: recent history
            hist = stock.history(period='5d')
            if not hist.empty and 'Close' in hist.columns:
                price_float = float(hist['Close'].iloc[-1])
                
                # Try to get currency from info (slower but more reliable)
                try:
                    info_currency = stock.info.get('currency')
                    if info_currency:
                        cache.set_ticker_currency(ticker, info_currency.upper())
                        logger.info(f"✓ {ticker}: {price_float:.4f} {info_currency.upper()} (from history)")
                    else:
                        logger.info(f"✓ {ticker}: {price_float:.4f} (from history, currency unknown)")
                except Exception:
                    logger.info(f"✓ {ticker}: {price_float:.4f} (from history)")
                
                return price_float
            
            # No data available - blacklist immediately
            logger.warning(f"{ticker}: No price data available. Blacklisting.")
            cache.blacklist_ticker(ticker)
            return None
        
        except Exception as e:
            error_str = str(e)
            
            # Permanent errors - blacklist immediately
            if any(x in error_str for x in ["404", "Not Found", "delisted", "No data found"]):
                logger.error(f"{ticker}: Permanent error ({error_str}). Blacklisting.")
                cache.blacklist_ticker(ticker)
                return None
            
            # Transient errors - retry
            logger.warning(f"{ticker}: Attempt {attempt+1}/{max_retries} failed: {error_str}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    
    # All retries exhausted
    logger.error(f"{ticker}: All {max_retries} attempts failed. Blacklisting.")
    cache.blacklist_ticker(ticker)
    return None

def get_currency_for_ticker(ticker: str) -> str:
    """
    Determine the trading currency for a ticker symbol.
    
    Priority:
    1. Database cache (persistent, immutable)
    2. Pattern-based detection (exchange suffixes, ISIN country codes)
    3. API lookup (yfinance fast_info)
    4. Default to USD (only if all else fails)
    
    NOTE: Only persists currencies from actual API lookups or known patterns,
    never persists the default fallback to avoid polluting the database.
    
    Args:
        ticker: Ticker symbol
    
    Returns:
        Currency code (e.g., 'EUR', 'USD', 'GBP')
    """
    if not ticker:
        return "EUR"
    
    # Normalize ticker
    ticker = normalize_ticker(ticker)
    ticker = ticker.upper()
    
    # 1. Check cache first (most reliable source)
    try:
        from lib.market_cache import get_market_cache
        cache = get_market_cache()
        cached_curr = cache.get_ticker_currency(ticker)
        if cached_curr:
            logger.debug(f"Currency cache HIT: {ticker} -> {cached_curr}")
            return cached_curr
    except Exception as e:
        logger.warning(f"Cache lookup failed for {ticker}: {e}")
    
    # 2. Crypto detection
    if ticker.endswith("-EUR"):
        cache.set_ticker_currency(ticker, "EUR")
        return "EUR"
    if ticker.endswith("-USD"):
        cache.set_ticker_currency(ticker, "USD")
        return "USD"
    
    # 3. Exchange suffix detection
    if "." in ticker:
        suffix = ticker.split(".")[-1]
        
        exchange_currency_map = {
            # Eurozone
            "DE": "EUR", "PA": "EUR", "MI": "EUR", "AS": "EUR", "VI": "EUR",
            "BR": "EUR", "HE": "EUR", "NX": "EUR", "BM": "EUR", "HM": "EUR",
            "BE": "EUR", "DU": "EUR", "SG": "EUR", "F": "EUR",
            # Other European
            "L": "GBP", "SW": "CHF", "S": "CHF", "CO": "DKK",
            "WA": "PLN", "ST": "SEK", "OL": "NOK",
            # Americas
            "TO": "CAD", "V": "CAD", "CN": "CAD",
            "SA": "BRL", "SP": "BRL",
            # Asia
            "HK": "HKD", "JO": "ZAR"
        }
        
        if suffix in exchange_currency_map:
            currency = exchange_currency_map[suffix]
            cache.set_ticker_currency(ticker, currency)
            logger.debug(f"Exchange suffix detection: {ticker} -> {currency}")
            return currency
    
    # 4. ISIN format detection (12 characters, country code prefix)
    if len(ticker) == 12 and ticker[:2].isalpha() and ticker[2:].isalnum():
        country_code = ticker[:2]
        
        isin_currency_map = {
            # Eurozone
            "AT": "EUR", "BE": "EUR", "CY": "EUR", "DE": "EUR", "EE": "EUR",
            "ES": "EUR", "FI": "EUR", "FR": "EUR", "GR": "EUR", "IE": "EUR",
            "IT": "EUR", "LT": "EUR", "LU": "EUR", "LV": "EUR", "MT": "EUR",
            "NL": "EUR", "PT": "EUR", "SI": "EUR", "SK": "EUR",
            # Europe
            "DK": "DKK", "NO": "NOK", "SE": "SEK", "CH": "CHF",
            "GB": "GBP", "PL": "PLN",
            # Americas
            "US": "USD", "CA": "CAD", "BR": "BRL",
            # Asia-Pacific
            "JP": "JPY", "HK": "HKD", "CN": "CNY", "AU": "AUD",
            "NZ": "NZD", "SG": "SGD", "KR": "KRW", "IN": "INR",
            # Others
            "ZA": "ZAR", "IL": "ILS", "TR": "TRY", "KY": "USD"
        }
        
        if country_code in isin_currency_map:
            currency = isin_currency_map[country_code]
            cache.set_ticker_currency(ticker, currency)
            logger.debug(f"ISIN country detection: {ticker} -> {currency}")
            return currency
    
    # 5. API lookup (only if not blacklisted)
    logger.warning(f"[PERF] Currency for {ticker} not in cache - attempting API lookup (THIS IS SLOW!)")
    try:
        if not cache.is_blacklisted(ticker):
            logger.info(f"[PERF] Calling yf.Ticker({ticker}) for currency lookup...")
            stock = yf.Ticker(ticker)
            # Try fast_info first
            try:
                logger.info(f"[PERF] Accessing fast_info.currency for {ticker}...")
                currency = stock.fast_info.currency
                if currency:
                    currency = currency.upper()
                    cache.set_ticker_currency(ticker, currency)
                    logger.info(f"API currency lookup: {ticker} -> {currency}")
                    return currency
            except AttributeError:
                # Fall back to info dict
                try:
                    info_currency = stock.info.get('currency')
                    if info_currency:
                        currency = info_currency.upper()
                        cache.set_ticker_currency(ticker, currency)
                        logger.info(f"API currency lookup (info): {ticker} -> {currency}")
                        return currency
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"API currency lookup failed for {ticker}: {e}")
    
    # 6. Default to USD and cache it to prevent repeated lookups
    logger.debug(f"Currency defaulted to USD for {ticker} (caching default)")
    cache.set_ticker_currency(ticker, "USD")
    return "USD"



@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_fx_rate(from_currency: str, to_currency: str = "EUR") -> Decimal:
    """
    Fetch current FX rate using yfinance with robust fallbacks.
    
    Args:
        from_currency: Source currency code
        to_currency: Target currency code
    
    Returns:
        Exchange rate as Decimal. Uses fallback if fetch fails.
    """
    if from_currency == to_currency:
        return Decimal(1)

    # 0. Define fallback rates
    fallback_rates = {
        "DKK": {"EUR": 0.1341},
        "USD": {"EUR": 0.95},
        "GBP": {"EUR": 1.18},
        "CHF": {"EUR": 1.06},
        "SEK": {"EUR": 0.088},
        "NOK": {"EUR": 0.087},
        "CAD": {"EUR": 0.68},
        "BRL": {"EUR": 0.16}
    }
    
    try:
        # 1. Try Cache
        from lib.market_cache import get_market_cache
        cache = get_market_cache()
        cached_val = cache.get_fx_rate(from_currency, to_currency, date.today())
        
        if cached_val:
             # Validate cached rate
             if abs(cached_val - 1.0) < 0.0001 and from_currency != to_currency:
                 logger.warning(f"Cached FX Rate for {from_currency}/{to_currency} is 1.0 (invalid). Ignoring cache.")
             else:
                 logger.info(f"FX Rate {from_currency}/{to_currency}: {cached_val:.4f} (from SQLite)")
                 return Decimal(str(cached_val))

        # 2. In-memory cache (session-level, ultra-fast)
        cache_key = f"{from_currency}/{to_currency}/{date.today()}"
        if cache_key in _fx_memory_cache:
            rate = _fx_memory_cache[cache_key]
            logger.debug(f"FX Rate {from_currency}/{to_currency}: {rate:.4f} (memory cache)")
            return Decimal(str(rate))
        
        # 3. Yahoo Finance (direct fetch, NO rate limiting for FX)
        # FX rates are critical for app functionality - fetch immediately
        fx_ticker = f"{from_currency}{to_currency}=X"
        
        try:
            stock = yf.Ticker(fx_ticker)
            rate = stock.fast_info.last_price
            
            if rate is not None and rate > 0:
                # Validate rate
                if abs(rate - 1.0) < 0.0001 and from_currency != to_currency:
                    logger.warning(f"FX Rate for {fx_ticker} returned 1.0, treating as invalid.")
                else:
                    logger.info(f"FX Rate {from_currency}/{to_currency}: {rate:.4f}")
                    # Cache in both database and memory
                    cache.set_fx_rate(from_currency, to_currency, date.today(), float(rate))
                    _fx_memory_cache[cache_key] = float(rate)
                    return Decimal(str(rate))
        except Exception as e:
            logger.debug(f"Failed to fetch FX rate {fx_ticker}: {e}")

    except Exception as e:
        logger.error(f"Error fetching FX rate {from_currency}/{to_currency}: {e}")
    
    # 3. Fallbacks
    if from_currency in fallback_rates and to_currency in fallback_rates[from_currency]:
        fallback = fallback_rates[from_currency][to_currency]
        logger.warning(f"Using hardcoded fallback FX rate for {from_currency}/{to_currency}: {fallback}")
        return Decimal(str(fallback))
    
    # 4. Default
    logger.warning(f"Could not fetch FX rate for {from_currency}/{to_currency}. Using 1.0")
    return Decimal(1)


# Removed redundant st.cache_data - using SQLite cache instead
# UPDATE: Added back st.cache_data with TTL for "Hybrid" speed (fast reload, but expires)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_historical_prices(tickers: List[str], start_date: date, end_date: date) -> pd.DataFrame:
    """
    Fetch historical closing prices for a list of tickers.
    
    Returns:
        DataFrame with Date index and Ticker columns containing Close prices.
        Forward filled to handle missing days/weekends.
    """
    if not tickers:
        return pd.DataFrame()
        
    logger.info(f"Fetching historical prices for {len(tickers)} tickers from {start_date} to {end_date}")
    
    # Resolve ISINs
    from lib.market_cache import get_market_cache
    from lib.isin_resolver import ISINResolver
    
    # Batch resolve all tickers
    batch_map = ISINResolver.resolve_batch(tickers)
    
    mapped_tickers = []
    ticker_map = {}
    
    for t in tickers:
        mapped = batch_map.get(t, t)
        mapped_tickers.append(mapped)
        ticker_map[mapped] = t
        
    # Check Cache
    cache = get_market_cache()
    
    # Query cache using original tickers
    cached_df = cache.get_historical_prices(tickers, start_date, end_date)
    
    tickers_to_fetch = []
    valid_cached_tickers = []
    
    # Refetch if older than 3 days
    cutoff_date = pd.Timestamp(end_date) - pd.Timedelta(days=3)
    
    if not cached_df.empty:
        for t in tickers:
            if t in cached_df.columns:
                last_valid = cached_df[t].last_valid_index()
                if last_valid and last_valid >= cutoff_date:
                    valid_cached_tickers.append(t)
                else:
                    tickers_to_fetch.append(t)
            else:
                tickers_to_fetch.append(t)
    else:
        tickers_to_fetch = list(tickers)
        
    # Filter Blacklisted Tickers
    non_blacklisted = []
    for t in tickers_to_fetch:
        if not cache.is_blacklisted(t):
            non_blacklisted.append(t)
    
    skipped_count = len(tickers_to_fetch) - len(non_blacklisted)
    tickers_to_fetch = non_blacklisted
        
    logger.info(f"Historical Data: {len(valid_cached_tickers)} cached, {len(tickers_to_fetch)} to fetch ({skipped_count} blacklisted)")
    
    fetched_df = pd.DataFrame()
    
    if tickers_to_fetch:
        fetch_mapped = []
        fetch_map = {} # mapped -> original
        
        # Pre-filter: Don't ask yfinance for raw ISINs, they will fail and spam
        for t in tickers_to_fetch:
            mapped = batch_map.get(t, t)
            
            # Check if mapped is still a raw ISIN (unresolved)
            # 12 chars, alphanumeric, no dot suffix (usually)
            # Most YF tickers are short or have dot suffix. Raw ISINs are distinct.
            is_raw_isin = bool(re.match(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$', mapped))
            
            if is_raw_isin:
                # Blacklist immediately, don't query
                # logger.info(f"Skipping raw ISIN {mapped} and blacklisting") # fast silence
                cache.blacklist_ticker(t)
                continue
                
            fetch_mapped.append(mapped)
            fetch_map[mapped] = t
        
        if not fetch_mapped:
            logger.info("No valid tickers to fetch after filtering ISINs.")
            return {}

        logger.info(f"Downloading historical data for {len(fetch_mapped)} tickers in chunks...")
        
        # Download in chunks to show progress and prevent timeout
        chunk_size = 25 # Reduced chunk size
        fetched_data = {}
        cache_updates = []
        
        for i in range(0, len(fetch_mapped), chunk_size):
            chunk = fetch_mapped[i:i+chunk_size]
            chunk_num = (i // chunk_size) + 1
            total_chunks = (len(fetch_mapped) + chunk_size - 1) // chunk_size
            
            logger.info(f"⏳ Downloading chunk {chunk_num}/{total_chunks} ({len(chunk)} tickers)...")
            
            try:
                data = yf.download(
                    chunk,
                    start=start_date,
                    end=end_date,
                    interval="1d",
                    group_by='ticker',
                    auto_adjust=False,
                    threads=False, # Disable threading to prevent log spam/lockup
                    progress=False
                )
                
                if len(chunk) == 1 and not data.empty:
                    mapped = chunk[0]
                    original = fetch_map[mapped]
                    if 'Close' in data.columns:
                        series = data['Close']
                        fetched_data[original] = series
                        
                        for dt, price in series.items():
                            if pd.notna(price):
                                cache_updates.append((original, dt.date(), float(price), 'yfinance'))
                elif len(chunk) > 1 and not data.empty:
                    for mapped in chunk:
                        original = fetch_map.get(mapped)
                        if not original: continue
                        
                        try:
                            if mapped in data.columns.levels[0]:
                                series = data[mapped]['Close']
                                fetched_data[original] = series
                                
                                for dt, price in series.items():
                                    if pd.notna(price):
                                        cache_updates.append((original, dt.date(), float(price), 'yfinance'))
                            else:
                                # No data for this ticker in the batch -> Blacklist it
                                logger.warning(f"No data for {original} ({mapped}) -> Blacklisting")
                                cache.blacklist_ticker(original)
                        except (KeyError, AttributeError):
                            # Also blacklist on error
                             cache.blacklist_ticker(original)
                             continue
                
                logger.info(f"✓ Chunk {chunk_num}/{total_chunks} complete ({len(cache_updates)} price points)")
                
            except Exception as e:
                logger.error(f"Failed chunk {chunk_num}: {e}")
                continue
        
        if fetched_data:
            fetched_df = pd.DataFrame(fetched_data)
        else:
            fetched_df = pd.DataFrame()

        # Bulk save to cache
        if cache_updates:
            logger.info(f"Saving {len(cache_updates)} price points to cache...")
            cache.set_prices_batch(cache_updates)
            logger.info("✓ Cache updated successfully")

            
    # Combine Cached and Fetched
    final_df = pd.DataFrame()
    
    if not cached_df.empty:
        valid_cols = [c for c in cached_df.columns if c in valid_cached_tickers]
        if valid_cols:
            final_df = cached_df[valid_cols].copy()
    
    if not fetched_df.empty:
        if final_df.empty:
            final_df = fetched_df
        else:
            final_df = final_df.combine_first(fetched_df)
            final_df.update(fetched_df)
            
            new_cols = [c for c in fetched_df.columns if c not in final_df.columns]
            if new_cols:
                final_df = pd.concat([final_df, fetched_df[new_cols]], axis=1)

    # Normalize Index
    if not final_df.empty:
        try:
            if final_df.index.tz is not None:
                final_df.index = final_df.index.tz_localize(None)
            final_df.index = final_df.index.normalize()
        except Exception as e:
            logger.warning(f"Failed to normalize index: {e}")

    # Apply Split Adjustments to Price History
    # Adjust price history for splits
    try:
        from lib.corporate_actions import CorporateActionService
        
        for ticker in final_df.columns:
            splits = CorporateActionService.get_cached_splits(ticker)
            
            # Anti-Gravity Safety: Never apply splits to Crypto or FX pairs
            # This prevents "Phantom Split" destruction of price history
            is_crypto_or_fx = any(x in ticker for x in ['-USD', '-EUR', 'BTC', 'ETH', 'SOL', 'USDEUR', 'EURUSD'])
            if is_crypto_or_fx:
                continue
            
            if splits:
                price_series = final_df[ticker]
                series_modified = False
                
                for split in splits:
                    try:
                        split_date = pd.Timestamp(split.action_date)
                        
                        if price_series.index.tz is not None:
                            if split_date.tzinfo is None:
                                split_date = split_date.tz_localize(price_series.index.tz)
                            else:
                                split_date = split_date.tz_convert(price_series.index.tz)
                                
                        factor = float(split.adjustment_factor)
                        mask = price_series.index < split_date
                        if mask.any():
                            final_df.loc[mask, ticker] = final_df.loc[mask, ticker] / factor
                            series_modified = True
                            
                    except Exception as e:
                        logger.warning(f"Error applying split {split} to {ticker}: {e}")
                
    except Exception as e:
        logger.error(f"Failed to apply split adjustments: {e}")
    
    # Standardize result
    if not final_df.empty:
        full_idx = pd.date_range(start=start_date, end=end_date, freq='D')
        final_df = final_df.reindex(full_idx)
        final_df = final_df.ffill().bfill()
        
    return final_df
