"""Market data service with yfinance integration and fallback strategies."""

import time
from decimal import Decimal
from typing import Dict, Optional, List
import pandas as pd
import yfinance as yf
import streamlit as st

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


# Ticker overrides for ISINs that yfinance doesn't handle correctly
TICKER_OVERRIDES = {
    # US ADRs - yfinance works better with ticker symbols than ISINs
    'US8740391003': 'TSM',  # Taiwan Semiconductor ADR
    'US02079K3059': 'GOOGL',  # Alphabet Class A
    'US0404131064': 'ARKK',  # ARK Innovation ETF
    
    # European ETFs - add .L suffix for London listing or use local ticker
    'IE000716YHJ7': 'FWRA.L',  # Invesco FTSE All-World UCITS ETF (London)
    'AT0000A0E9W5': 'SPIW.DE',  # Example - adjust as needed
}


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_prices(tickers: List[str]) -> Dict[str, Optional[float]]:
    """
    Fetch current prices from yfinance with error handling and retry logic.
    
    Args:
        tickers: List of ticker symbols (Yahoo Finance format)
    
    Returns:
        Dictionary mapping ticker to current price (EUR) or None if failed
    """
    logger.info(f"Fetching prices for {len(tickers)} tickers")
    
    # Apply ticker overrides
    mapped_tickers = []
    ticker_map = {}  # original -> mapped
    for ticker in tickers:
        mapped = TICKER_OVERRIDES.get(ticker, ticker)
        if mapped != ticker:
            logger.info(f"Ticker override: {ticker} -> {mapped}")
        mapped_tickers.append(mapped)
        ticker_map[mapped] = ticker  # Reverse map for results
    
    prices = {}
    
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
                    prices[original_ticker] = float(price)  # Map back to original
                    logger.info(f"{original_ticker}: {price:.2f}")
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
                                prices[original_ticker] = float(price)  # Map back
                                logger.info(f"{original_ticker}: {price:.2f}")
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
        # Fallback: fetch individually using ORIGINAL tickers (with override logic inside fetch_single_price)
        for original_ticker in tickers:
            mapped_ticker = TICKER_OVERRIDES.get(original_ticker, original_ticker)
            price = fetch_single_price(mapped_ticker)
            prices[original_ticker] = price  # Store with original key
    
    success_count = sum(1 for p in prices.values() if p is not None)
    logger.info(f"Successfully fetched {success_count}/{len(tickers)} prices")
    
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
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt)  # Exponential backoff
                logger.warning(f"{ticker}: Attempt {attempt + 1} failed, retrying in {wait_time}s - {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"{ticker}: All {max_retries} attempts failed - {e}")
                return None
    
    return None


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
