"""
Multi-Provider Market Data Service

Provides fallback support for market data from multiple sources:
- Yahoo Finance (yfinance) - Primary
- Alpha Vantage - Fallback for US/global stocks
- Finnhub - Fallback for international stocks
- OpenFIGI - ISIN resolution service

Designed for extensibility and easy addition of new providers.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from decimal import Decimal
from datetime import date
import os
import streamlit as st

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""
    
    @abstractmethod
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        pass
    
    @abstractmethod
    def resolve_isin(self, isin: str) -> Optional[str]:
        """Resolve ISIN to ticker symbol."""
        pass
    
    @abstractmethod
    def get_historical_price(self, symbol: str, date: date) -> Optional[float]:
        """Get historical price for a specific date."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass


class AlphaVantageProvider(MarketDataProvider):
    """Alpha Vantage market data provider."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        
        # Also check Streamlit secrets (nested under passwords as per user config)
        if not self.api_key and hasattr(st, "secrets"):
            if "passwords" in st.secrets and "ALPHA_VANTAGE_API_KEY" in st.secrets["passwords"]:
                self.api_key = st.secrets["passwords"]["ALPHA_VANTAGE_API_KEY"]
            elif "ALPHA_VANTAGE_API_KEY" in st.secrets:
                 self.api_key = st.secrets["ALPHA_VANTAGE_API_KEY"]
                 
        self._enabled = self.api_key is not None and len(self.api_key) > 5
    
    @property
    def name(self) -> str:
        return "Alpha Vantage"
    
    def get_price(self, symbol: str) -> Optional[float]:
        if not self._enabled:
            return None
        
        try:
            import requests
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': symbol,
                'apikey': self.api_key
            }
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'Global Quote' in data and '05. price' in data['Global Quote']:
                price = float(data['Global Quote']['05. price'])
                logger.info(f"{self.name}: {symbol} = {price}")
                return price
        except Exception as e:
            logger.warning(f"{self.name} error for {symbol}: {e}")
        
        return None
    
    def resolve_isin(self, isin: str) -> Optional[str]:
        # Alpha Vantage doesn't provide ISIN resolution
        return None
    
    def get_historical_price(self, symbol: str, date: date) -> Optional[float]:
        if not self._enabled:
            return None
        
        try:
            import requests
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': symbol,
                'apikey': self.api_key,
                'outputsize': 'compact'
            }
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'Time Series (Daily)' in data:
                date_str = date.strftime('%Y-%m-%d')
                if date_str in data['Time Series (Daily)']:
                    price = float(data['Time Series (Daily)'][date_str]['4. close'])
                    return price
        except Exception as e:
            logger.warning(f"{self.name} historical price error for {symbol}: {e}")
        
        return None


class FinnhubProvider(MarketDataProvider):
    """Finnhub market data provider (good for international stocks)."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('FINNHUB_API_KEY')

        # Also check Streamlit secrets (nested under passwords as per user config)
        if not self.api_key and hasattr(st, "secrets"):
            if "passwords" in st.secrets and "FINNHUB_API_KEY" in st.secrets["passwords"]:
                self.api_key = st.secrets["passwords"]["FINNHUB_API_KEY"]
            elif "FINNHUB_API_KEY" in st.secrets:
                 self.api_key = st.secrets["FINNHUB_API_KEY"]

        self._enabled = self.api_key is not None and len(self.api_key) > 5
    
    @property
    def name(self) -> str:
        return "Finnhub"
    
    def get_price(self, symbol: str) -> Optional[float]:
        if not self._enabled:
            return None
        
        try:
            import requests
            url = f"https://finnhub.io/api/v1/quote"
            params = {
                'symbol': symbol,
                'token': self.api_key
            }
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'c' in data and data['c'] > 0:  # 'c' is current price
                price = float(data['c'])
                logger.info(f"{self.name}: {symbol} = {price}")
                return price
        except Exception as e:
            logger.warning(f"{self.name} error for {symbol}: {e}")
        
        return None
    
    def resolve_isin(self, isin: str) -> Optional[str]:
        """Finnhub can search by ISIN."""
        if not self._enabled:
            return None
        
        try:
            import requests
            url = f"https://finnhub.io/api/v1/search"
            params = {
                'q': isin,
                'token': self.api_key
            }
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            
            if 'result' in data and len(data['result']) > 0:
                # Return first match
                ticker = data['result'][0]['symbol']
                logger.info(f"{self.name} resolved ISIN {isin} -> {ticker}")
                return ticker
        except Exception as e:
            logger.warning(f"{self.name} ISIN resolution error for {isin}: {e}")
        
        return None
    
    def get_historical_price(self, symbol: str, date: date) -> Optional[float]:
        # Finnhub requires start/end timestamps for candles
        # Simplified implementation
        return None


class MarketDataAggregator:
    """
    Aggregates multiple market data providers with fallback support.
    
    FREE TIER REALITY:
    - Yahoo Finance: Global coverage (primary, always used)
    - Alpha Vantage: US stocks only (25 req/day)
    - Finnhub: US stocks primarily (60 req/min)
    
    For European stocks: Yahoo Finance with proper exchange suffixes (.DE, .L, .PA)
    is the best free option.
    """
    
    def __init__(self):
        self.providers: List[MarketDataProvider] = [
            AlphaVantageProvider(),  # US stocks fallback
            FinnhubProvider(),       # US stocks fallback
        ]
        
        # Filter to only enabled providers
        self.providers = [p for p in self.providers if hasattr(p, '_enabled') and p._enabled]
        
        if self.providers:
            logger.info(f"Initialized {len(self.providers)} fallback providers: {[p.name for p in self.providers]}")
        else:
            logger.info("No fallback providers configured (all require API keys)")
    
    def get_price_with_fallback(self, symbol: str) -> Optional[float]:
        """Try each provider until one succeeds."""
        for provider in self.providers:
            try:
                price = provider.get_price(symbol)
                if price is not None and price > 0:
                    return price
            except Exception as e:
                logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                continue
        
        return None
    
    def resolve_isin_with_fallback(self, isin: str) -> Optional[str]:
        """Try to resolve ISIN using fallback providers."""
        for provider in self.providers:
            try:
                ticker = provider.resolve_isin(isin)
                if ticker:
                    return ticker
            except Exception as e:
                logger.warning(f"Provider {provider.name} ISIN resolution failed for {isin}: {e}")
                continue
        
        return None
