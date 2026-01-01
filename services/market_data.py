"""Market data service with yfinance integration and fallback strategies."""

from datetime import date
from decimal import Decimal
from typing import Dict, Optional, List
import pandas as pd
import yfinance as yf
import streamlit as st

from utils.logging_config import setup_logger, get_perf_logger
from services.isin_resolver import ISINResolver
from services.multi_provider import MarketDataAggregator

logger = setup_logger(__name__)

# Initialize fallback providers
_fallback_aggregator = MarketDataAggregator()


# Removed redundant st.cache_data - using SQLite cache instead
def fetch_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    """
    Fetch current prices from yfinance with error handling and retry logic.
    Uses SQLite cache to minimize API calls.
    
    Args:
        tickers: List of ticker symbols (Yahoo Finance format)
    
    Returns:
        Dictionary mapping ticker to current price (EUR) or None if failed
    """
    from services.market_cache import get_market_cache
    
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

            mapped_tickers.append(resolved_ticker)
            ticker_map[resolved_ticker] = original_ticker  # Reverse map
        
        if not mapped_tickers:
            return prices
        
        # Batch fetch for efficiency
        try:
            data = yf.download(
                mapped_tickers,
                period='1d',
                interval='1d',
                group_by='ticker',
                threads=True,
                progress=False
            )
            
            # Handle single ticker vs multiple tickers
            if len(mapped_tickers) == 1:
                mapped_ticker = mapped_tickers[0]
                original_ticker = ticker_map.get(mapped_ticker, mapped_ticker)
                if not data.empty and 'Close' in data.columns:
                    price = data['Close'].iloc[-1]
                    if price is not None and not pd.isna(price):
                        price_val = float(price)
                        prices[original_ticker] = price_val
                        cache.set_price(original_ticker, price_val, today)
                        logger.info(f"{original_ticker}: {price_val:.2f}")
                    else:
                        prices[original_ticker] = None
                        logger.warning(f"{original_ticker}: No current price available")
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
                                price = ticker_data['Close'].iloc[-1]
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
    Fetch price for a single ticker with retry logic and fallbacks.
    
    Fallback chain:
    1. Current price (1d)
    2. Historical price (5d)
    3. None
    """
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Try different price fields
            price_fields = ['currentPrice', 'regularMarketPrice', 'previousClose']
            for field in price_fields:
                price = info.get(field)
                if price is not None and price > 0:
                    logger.info(f"{ticker}: {price:.2f} (from {field})")
                    return float(price)
            
            # Fallback: historical data
            hist = stock.history(period='5d')
            if not hist.empty and 'Close' in hist.columns:
                price = hist['Close'].iloc[-1]
                if price is not None and price > 0:
                    logger.info(f"{ticker}: {price:.2f} (from historical)")
                    return float(price)
            
            return None
            
        except Exception as e:
            logger.warning(f"Error fetching SINGLE price for {ticker}: {e}")
            return None

def get_currency_for_ticker(ticker: str) -> str:
    """
    Determine the trading currency based on the ticker symbol.
    Defaults to USD if cannot determine.
    """
    if not ticker:
        return "EUR"
        
    ticker = ticker.upper()
    
    # 1. Crypto
    if ticker.endswith("-EUR"):
        return "EUR"
    if ticker.endswith("-USD"):
        return "USD"
        
    # 2. Exchange Suffixes
    if "." in ticker:
        suffix = ticker.split(".")[-1]
        
        if suffix in ["DE", "PA", "MI", "AS", "VI", "BR", "HE", "NX", "BM", "HM", "BE", "DU", "SG", "F"]:
            return "EUR"
        if suffix == "L":
            return "GBP"
        if suffix in ["TO", "V", "CN"]:
            return "CAD"
        if suffix in ["SW", "S"]:
            return "CHF"
        if suffix == "HK":
            return "HKD"
        if suffix == "JO":
            return "ZAR"
        if suffix in ["SA", "SP"]:
            return "BRL"
        if suffix == "CO":
            return "DKK"
        if suffix == "WA":
            return "PLN"
        if suffix == "ST":
            return "SEK"
        if suffix == "OL":
            return "NOK"
    
    # 3. ISIN format detection (12 characters, starts with 2-letter country code)
    if len(ticker) == 12 and ticker[:2].isalpha() and ticker[2:].isalnum():
        country_code = ticker[:2]
        
        # Map ISIN country codes to currencies
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
        
        currency = isin_currency_map.get(country_code)
        if currency:
            return currency
    
    # 4. Default to USD for US-style tickers
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
        from services.market_cache import get_market_cache
        cache = get_market_cache()
        cached_val = cache.get_fx_rate(from_currency, to_currency, date.today())
        
        if cached_val:
             # Validate cached rate
             if abs(cached_val - 1.0) < 0.0001 and from_currency != to_currency:
                 logger.warning(f"Cached FX Rate for {from_currency}/{to_currency} is 1.0 (invalid). Ignoring cache.")
             else:
                 logger.info(f"FX Rate {from_currency}/{to_currency}: {cached_val:.4f} (from SQLite)")
                 return Decimal(str(cached_val))

        # 2. Yahoo Finance
        fx_ticker = f"{from_currency}{to_currency}=X"
        rate = fetch_single_price(fx_ticker)
        
        # Validate rate
        if rate is not None:
            if abs(rate - 1.0) < 0.0001 and from_currency != to_currency:
                logger.warning(f"FX Rate for {fx_ticker} returned 1.0, treating as invalid.")
                rate = None
            else:
                logger.info(f"FX Rate {from_currency}/{to_currency}: {rate:.4f}")
                # Cache successful fetch
                cache.set_fx_rate(from_currency, to_currency, date.today(), rate)
                return Decimal(str(rate))

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
    from services.market_cache import get_market_cache
    from services.isin_resolver import ISINResolver
    
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
        
    logger.info(f"Historical Data: {len(valid_cached_tickers)} cached, {len(tickers_to_fetch)} to fetch")
    
    fetched_df = pd.DataFrame()
    
    if tickers_to_fetch:
        fetch_mapped = []
        fetch_map = {} # mapped -> original
        for t in tickers_to_fetch:
            mapped = batch_map.get(t, t)
            fetch_mapped.append(mapped)
            fetch_map[mapped] = t
            
        try:
            data = yf.download(
                fetch_mapped,
                start=start_date,
                end=end_date,
                interval="1d",
                group_by='ticker',
                auto_adjust=False,
                threads=True,
                progress=False
            )
            
            fetched_data = {}
            cache_updates = []
            
            if len(fetch_mapped) == 1:
                mapped = fetch_mapped[0]
                original = fetch_map[mapped]
                if 'Close' in data.columns:
                    series = data['Close']
                    fetched_data[original] = series
                    
                    for dt, price in series.items():
                        if pd.notna(price):
                            cache_updates.append((original, dt.date(), float(price), 'yfinance'))
            else:
                for mapped in fetch_mapped:
                    original = fetch_map.get(mapped)
                    if not original: continue
                    
                    if mapped in data.columns.levels[0]:
                        series = data[mapped]['Close']
                        fetched_data[original] = series
                        
                        for dt, price in series.items():
                            if pd.notna(price):
                                cache_updates.append((original, dt.date(), float(price), 'yfinance'))
            
            if fetched_data:
                fetched_df = pd.DataFrame(fetched_data, index=data.index)
            else:
                fetched_df = pd.DataFrame(index=data.index)

            # Bulk save to cache
            if cache_updates:
                cache.set_prices_batch(cache_updates)
                
        except Exception as e:
            logger.error(f"Failed to fetch historical prices: {e}")
            
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
        from services.corporate_actions import CorporateActionService
        
        for ticker in final_df.columns:
            splits = CorporateActionService.get_cached_splits(ticker)
            
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
