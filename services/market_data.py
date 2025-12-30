"""Market data service with yfinance integration and fallback strategies."""

import time
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


# Initialize fallback providers
_fallback_aggregator = MarketDataAggregator()


@st.cache_data(ttl=300)  # Cache for 5 minutes
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
        # Step 0: Check cache first
        cache = get_market_cache()
        today = date.today()
        
        # Try to get all prices from cache
        cached_prices = cache.get_prices_batch(tickers, today)
        
        # Separate tickers into cached and needs-fetch
        tickers_to_fetch = [t for t, p in cached_prices.items() if p is None]
        prices = {t: p for t, p in cached_prices.items() if p is not None}
        
        if not tickers_to_fetch:
            logger.info(f"All {len(tickers)} prices served from cache!")
            return prices
        
        logger.info(f"Cache: {len(prices)} hits, {len(tickers_to_fetch)} to fetch from API")
        
        # Step 1: Resolve ISINs to tickers
        # ISINResolver now handles overrides internally
        mapped_tickers = []
        ticker_map = {}  # mapped -> original
        
        # Batch resolve all needed tickers
        batch_map = ISINResolver.resolve_batch(tickers_to_fetch)
        
        for original_ticker in tickers_to_fetch:
            # Use batched result
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
                mapped_tickers,  # Use mapped tickers
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
                        cache.set_price(original_ticker, price_val, today)  # Cache it
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
                                    cache.set_price(original_ticker, price_val, today)  # Cache it
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
            # Fallback: fetch individually using ORIGINAL tickers
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
                    cache.set_price(original_ticker, price, today)  # Cache it
                
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
    3. None (caller should handle)
    
    Args:
        ticker: Ticker symbol
        max_retries: Maximum number of retry attempts
    
    Returns:
        Current price or None if all attempts failed
    """
    for attempt in range(max_retries):
        try:
            # Try current price
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
            
            logger.warning(f"{ticker}: No price data available")
            return None
            
        except Exception as e:
            logger.warning(f"Error fetching SINGLE price for {ticker}: {e}")
            return None

def get_currency_for_ticker(ticker: str) -> str:
    """
    Determine the trading currency based on the ticker symbol.
    
    Rules:
    - Suffix .DE, .PA, .MI, .AS, .VI, .BR, .HE, .NX -> EUR
    - Suffix .L -> GBP (Note: might be GBp/pencil, handled separately?)
    - Suffix .TO, .V -> CAD
    - Suffix .SW -> CHF
    - Suffix .HK -> HKD
    - Suffix -EUR -> EUR (Crypto)
    - Suffix -USD -> USD (Crypto)
    - No suffix -> USD (US Market default)
    """
    if not ticker:
        return "EUR"
        
    ticker = ticker.upper()
    
    # 1. Crypto explicit
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
            return "GBP" # Potential GBp issue, but assume GBP for FX lookup for now
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
    
    # 3. Default to USD for US-style tickers (no suffix)
    return "USD"


@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_fx_rate(from_currency: str, to_currency: str = "EUR") -> Decimal:
    """
    Fetch current FX rate using yfinance.
    
    Args:
        from_currency: Source currency code (e.g., 'USD')
        to_currency: Target currency code (default: 'EUR')
    
    Returns:
        Exchange rate as Decimal, or 1.0 if same currency or fetch fails
    """
    if from_currency == to_currency:
        return Decimal(1)
    
    try:
        # Yahoo Finance FX format: USDEUR=X
        fx_ticker = f"{from_currency}{to_currency}=X"
        rate = fetch_single_price(fx_ticker)
        
        if rate is not None:
            logger.info(f"FX Rate {from_currency}/{to_currency}: {rate:.4f}")
            return Decimal(str(rate))
        else:
            logger.warning(f"Could not fetch FX rate for {fx_ticker}, using 1.0")
            return Decimal(1)
            
    except Exception as e:
        logger.error(f"Error fetching FX rate {from_currency}/{to_currency}: {e}")
        return Decimal(1)


@st.cache_data(ttl=3600)  # Cache for 1 hour
def fetch_historical_prices(tickers: List[str], start_date: date, end_date: date) -> pd.DataFrame:
    """
    Fetch historical closing prices for a list of tickers.
    
    Args:
        tickers: List of ticker symbols
        start_date: Start date
        end_date: End date
        
    Returns:
        DataFrame with Date index and Ticker columns containing Close prices.
        Forward filled to handle missing days/weekends.
    """
    if not tickers:
        return pd.DataFrame()
        
    logger.info(f"Fetching historical prices for {len(tickers)} tickers from {start_date} to {end_date}")
    
    # Resolve ISINs
    from services.market_cache import get_market_cache
    
    # Resolve ISINs first
    mapped_tickers = []
    ticker_map = {}
    
    # Import locally to avoid circular imports if any
    from services.isin_resolver import ISINResolver
    
    # Batch resolve all tickers
    batch_map = ISINResolver.resolve_batch(tickers)
    
    mapped_tickers = []
    ticker_map = {}
    
    for t in tickers:
        mapped = batch_map.get(t, t)
        mapped_tickers.append(mapped)
        ticker_map[mapped] = t
        
    unique_mapped = list(set(mapped_tickers))
    
    # 1. Check Cache
    cache = get_market_cache()
    
    # Query cache using original tickers (since that's how we store them)
    cached_df = cache.get_historical_prices(tickers, start_date, end_date)
    
    tickers_to_fetch = []
    valid_cached_tickers = []
    
    # Check staleness/missing
    cutoff_date = pd.Timestamp(end_date) - pd.Timedelta(days=3)  # Re-fetch if older than 3 days
    
    if not cached_df.empty:
        for t in tickers:
            if t in cached_df.columns:
                # Check lateness
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
        # Map these specific tickers
        fetch_mapped = []
        fetch_map = {} # mapped -> original
        for t in tickers_to_fetch:
            # Use the pre-calculated batch_map
            mapped = batch_map.get(t, t)
            fetch_mapped.append(mapped)
            fetch_map[mapped] = t
            
        try:
            # Fetch data
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
            
            # Process result
            fetched_data = {}
            
            # Prepare for batch cache update
            cache_updates = []
            
            if len(fetch_mapped) == 1:
                mapped = fetch_mapped[0]
                original = fetch_map[mapped]
                if 'Close' in data.columns:
                    series = data['Close']
                    fetched_data[original] = series
                    
                    # Prepare cache data
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
                        
                        # Prepare cache data
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
    # We prioritize Fetched (newer) over Cached if overlap
    
    final_df = pd.DataFrame()
    
    # Start with cached data for valid tickers
    if not cached_df.empty:
        # Only keep valid columns
        valid_cols = [c for c in cached_df.columns if c in valid_cached_tickers]
        if valid_cols:
            final_df = cached_df[valid_cols].copy()
    
    # Combine with fetched
    if not fetched_df.empty:
        # If final_df is empty, just use fetched
        if final_df.empty:
            final_df = fetched_df
        else:
            # Combine/update
            final_df = final_df.combine_first(fetched_df)
            # Or distinct update?
            # We want to overwrite with fetched_df where it exists
            final_df.update(fetched_df)
            
            # Add any new columns that weren't in final_df
            new_cols = [c for c in fetched_df.columns if c not in final_df.columns]
            if new_cols:
                final_df = pd.concat([final_df, fetched_df[new_cols]], axis=1)

    # Normalize Index to remove timezones (ensure Naive) for consistent split comparison
    if not final_df.empty:
        try:
            if final_df.index.tz is not None:
                final_df.index = final_df.index.tz_localize(None)
            final_df.index = final_df.index.normalize()
        except Exception as e:
            logger.warning(f"Failed to normalize index: {e}")

    # ----------------------------------------------------
    # CRITICAL: Apply Split Adjustments to Price History
    # ----------------------------------------------------
    # Since transactions are back-adjusted (shares increased in the past),
    # price history must also be back-adjusted (prices decreased in the past).
    # We use CorporateActionService to get verified/blacklisted splits.
    
    try:
        # Import inside function to avoid potential circular initializations
        from services.corporate_actions import CorporateActionService
        
        # Apply only to columns in final_df
        for ticker in final_df.columns:
            # Get split history using same logic as transaction adjustment
            splits = CorporateActionService.get_cached_splits(ticker)
            
            if splits:
                price_series = final_df[ticker]
                series_modified = False
                
                # Sort splits by date descending (latest first)
                # But for back-adjustment, we iterate through all splits.
                # Logic: If split happened on Date S, then ALL prices < Date S
                # must be divided by the split ratio.
                
                for split in splits:
                    try:
                        split_date = pd.Timestamp(split.action_date)
                        
                        # Handle timezone if index is aware
                        if price_series.index.tz is not None:
                            if split_date.tzinfo is None:
                                split_date = split_date.tz_localize(price_series.index.tz)
                            else:
                                split_date = split_date.tz_convert(price_series.index.tz)
                                
                        factor = float(split.adjustment_factor)
                        
                        logger.debug(f"Checking split for {ticker}: Date={split_date}, Factor={factor}")
                        
                        mask = price_series.index < split_date
                        if mask.any():
                            # Apply adjustment
                            final_df.loc[mask, ticker] = final_df.loc[mask, ticker] / factor
                            series_modified = True
                            logger.info(f"APPLIED SPLIT for {ticker}: Divided prices before {split_date.date()} by {factor}")
                        else:
                            logger.debug(f"No prices found before split date {split_date} for {ticker}")
                            
                    except Exception as e:
                        logger.warning(f"Error applying split {split} to {ticker}: {e}")
                
                if series_modified:
                    logger.info(f"Successfully back-adjusted price history for {ticker}")
                    
    except Exception as e:
        logger.error(f"Failed to apply split adjustments: {e}")
    
    # Standardize result
    if not final_df.empty:
        # Determine frequency to reindex (daily)
        full_idx = pd.date_range(start=start_date, end=end_date, freq='D')
        final_df = final_df.reindex(full_idx)
        final_df = final_df.ffill().bfill()
        
    return final_df
