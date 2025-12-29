"""
Clear Split Cache for Specific Tickers

Use this script to remove incorrect split data from the cache.
"""

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
        
        # Clear using the cache method
        deleted = cache.clear_splits(ticker)
        print(f"  OK - Cleared {deleted} records")
        print()
    
    print("=" * 60)
    print("Done! Restart the app to re-fetch split data.")
    print()
    print("To prevent automatic split fetching, you can:")
    print("1. Set fetch_splits=False in portfolio_viewer.py (line ~186)")
    print("2. Or manually edit this script to not fetch problematic tickers")
    print("=" * 60)

if __name__ == "__main__":
    # Add tickers here that have incorrect split data
    # Note: BYD splits are dated in the future (2025-07-30, 2025-06-10)
    # which incorrectly adjusts all historical transactions
    tickers_to_clear = [
        'CNE100000296',  # BYD - has incorrect future-dated splits
        # Add more tickers as needed
    ]
    
    clear_splits(tickers_to_clear)
