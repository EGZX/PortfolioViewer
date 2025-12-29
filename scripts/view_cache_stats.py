"""
View Market Cache Statistics

This script displays cache statistics to help monitor cache performance.
"""

from services.market_cache import get_market_cache
from pathlib import Path
import sys

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

def main():
    print("=" * 60)
    print("Market Cache Statistics")
    print("=" * 60)
    print()
    
    # Check if database exists
    db_path = Path("data/market_cache.db")
    if not db_path.exists():
        print("[!] Cache database not found!")
        print(f"    Expected location: {db_path.absolute()}")
        print()
        print("[i] The cache will be created on first run of the app.")
        return
    
    # Get cache instance
    try:
        cache = get_market_cache()
        stats = cache.get_stats()
        
        print(f"[*] Database Location: {db_path.absolute()}")
        print(f"[*] Database Size: {db_path.stat().st_size / 1024:.1f} KB")
        print()
        
        print("Cache Statistics:")
        print(f"   - Total prices cached: {stats['total_prices']:,}")
        print(f"   - Unique tickers: {stats['unique_tickers']:,}")
        print(f"   - Stock splits cached: {stats['total_splits']:,}")
        print()
        
        if stats['total_prices'] > 0:
            avg_prices_per_ticker = stats['total_prices'] / stats['unique_tickers']
            print(f"Average prices per ticker: {avg_prices_per_ticker:.1f}")
            print()
        
        # Check if encryption is enabled
        if cache.cipher:
            print("Encryption: ENABLED")
        else:
            print("Encryption: DISABLED")
            print("   [i] Run 'python generate_cache_key.py' to enable encryption")
        
        print()
        print("=" * 60)
        
    except Exception as e:
        print(f"[!] Error reading cache: {e}")
        print()
        print("This might indicate a corrupted database.")
        print("Try deleting 'data/market_cache.db' and restarting the app.")

if __name__ == "__main__":
    main()
