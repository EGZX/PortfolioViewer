"""
Crypto price fetcher using CoinGecko free API.
No API key required.
"""

import requests
from decimal import Decimal
from typing import Optional, Dict
from datetime import datetime
import time

from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)

# CoinGecko API endpoint
COINGECKO_API = "https://api.coingecko.com/api/v3"

# Ticker to CoinGecko ID mapping
CRYPTO_ID_MAP = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'USDT': 'tether',
    'USDC': 'usd-coin',
    'BNB': 'binancecoin',
    'XRP': 'ripple',
    'ADA': 'cardano',
    'DOGE': 'dogecoin',
    'DOT': 'polkadot',
    'MATIC': 'matic-network',
    'AVAX': 'avalanche-2',
    'LINK': 'chainlink',
}

def get_crypto_price(ticker: str, target_currency: str = "EUR") -> Optional[float]:
    """
    Fetch current crypto price from CoinGecko.
    
    Args:
        ticker: Crypto ticker (e.g., 'BTC', 'ETH')
        target_currency: Target currency (default: EUR)
        
    Returns:
        Price as float, or None if failed
    """
    # Normalize ticker
    ticker = ticker.upper().strip()
    
    # Get CoinGecko ID
    coin_id = CRYPTO_ID_MAP.get(ticker)
    if not coin_id:
        logger.warning(f"Unknown crypto ticker: {ticker}")
        return None
    
    try:
        # CoinGecko simple price endpoint
        url = f"{COINGECKO_API}/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': target_currency.lower()
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract price
        if coin_id in data and target_currency.lower() in data[coin_id]:
            price = float(data[coin_id][target_currency.lower()])
            logger.info(f"Crypto price: {ticker} = €{price:,.2f}")
            return price
        else:
            logger.warning(f"No price data for {ticker} in {target_currency}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching {ticker} price from CoinGecko")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {ticker} price from CoinGecko: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {ticker}: {e}")
        return None


def get_crypto_prices_batch(tickers: list, target_currency: str = "EUR") -> Dict[str, Optional[float]]:
    """
    Fetch multiple crypto prices in one API call.
    
    Args:
        tickers: List of crypto tickers
        target_currency: Target currency (default: EUR)
        
    Returns:
        Dict mapping ticker to price
    """
    if not tickers:
        return {}
    
    # Normalize and map tickers
    ticker_map = {}
    coin_ids = []
    
    for ticker in tickers:
        ticker = ticker.upper().strip()
        coin_id = CRYPTO_ID_MAP.get(ticker)
        if coin_id:
            ticker_map[coin_id] = ticker
            coin_ids.append(coin_id)
    
    if not coin_ids:
        return {t: None for t in tickers}
    
    try:
        # Batch request
        url = f"{COINGECKO_API}/simple/price"
        params = {
            'ids': ','.join(coin_ids),
            'vs_currencies': target_currency.lower()
        }
        
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        
        # Build result
        result = {}
        for coin_id, ticker in ticker_map.items():
            if coin_id in data and target_currency.lower() in data[coin_id]:
                price = float(data[coin_id][target_currency.lower()])
                result[ticker] = price
                logger.info(f"Crypto price: {ticker} = €{price:,.2f}")
            else:
                result[ticker] = None
                logger.warning(f"No price for {ticker}")
       
        return result
        
    except Exception as e:
        logger.error(f"Error fetching crypto prices: {e}")
        return {t: None for t in tickers}


def is_crypto_ticker(ticker: str) -> bool:
    """Check if ticker is a known crypto."""
    return ticker.upper().strip() in CRYPTO_ID_MAP
