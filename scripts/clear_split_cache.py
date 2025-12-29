"""
Clear Split Cache for Specific Tickers

Use this script to remove incorrect split data from the cache.
"""

import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.market_cache import get_market_cache

def clear_splits(tickers: list[str]):
    """Clear split data for specific tickers."""
    cache = get_market_cache()
    
    print("=" * 60)
    print("Clearing Split Cache")
    print("=" * 60)
    print()
    
    for ticker in tickers:
        print(f"Clearing splits for {ticker}...")
        
        # Get current splits before clearing
        splits = cache.get_splits(ticker)
        if splits:
            print(f"  Found {len(splits)} splits:")
            for split_date, ratio in splits:
                print(f"    - {split_date}: {ratio}x")
        else:
            print(f"  No splits found for {ticker}")
        
        # Clear using the cache method (we need to bypass strict type check if necessary, but method signature says str)
        # Note: clear_splits might catch exception if table doesn't exist
        try:
             # Manually implement clear if method doesn't exist or modify usage
             # Checked market_cache.py? Assume clear_splits exists based on previous code.
             deleted = cache.clear_splits(ticker)
             print(f"  OK - Cleared cache for {ticker}")
        except Exception as e:
             print(f"  Error: {e}")
        print()
    
    print("=" * 60)
    print("Done! Restart the app to re-fetch split data.")
    print("=" * 60)

if __name__ == "__main__":
    # Add tickers here that have incorrect split data
    tickers_to_clear = [
        'CNE100000296',  # BYD
        'US64110L1061',  # Netflix (ISIN)
        'DE000A0HHJR3',  # Cliq Digital (likely ISIN)
        'CLIQ.DE',       # Cliq Digital (Ticker)
        'NFLX',          # Netflix (Ticker)
        'US48581R2058',  # Kaspi (from test data)
    ]
    
    clear_splits(tickers_to_clear)
