
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parsers.csv_parser import CSVParser
from calculators.portfolio import Portfolio
from parsers.enhanced_transaction import TransactionType, AssetType
from services.corporate_actions import CorporateActionService

def analyze():
    # Use pathlib for portable path handling
    BASE_DIR = Path(__file__).resolve().parents[1]  # project root
    file_path = BASE_DIR / "Testdata" / "Deine Gesamtansicht-20251229-055109.csv"
    
    print(f"Loading {file_path}...")
    
    # Parse with error handling
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except FileNotFoundError as e:
        print(f"ERROR: CSV file not found: {file_path}")
        print(f"Please ensure the file exists or update the path.")
        raise
    
    parser = CSVParser()
    transactions = parser.parse_csv(content)
    print(f"Parsed {len(transactions)} total transactions.")
    
    # Filter for specific tickers
    targets = {
        'BYD': ['CNE100000296', '1211.HK', 'BYD'],
        'CLIQ': ['DE000A0HHJR3', 'CLIQ.DE', 'CLIQ'],
        'NFLX': ['US64110L1061', 'NFLX']
    }
    
    print("\n" + "="*50)
    print("DETAILED TRANSACTION ANALYSIS")
    print("="*50)
    
    for name, identifiers in targets.items():
        print(f"\nAnalyzing {name} (ids: {identifiers}):")
        # Strengthen matching to prevent false positives (e.g., BYD-ETF matching BYD)
        ident_set = {i.upper() for i in identifiers}
        related_tx = [
            t for t in transactions 
            if (t.isin and t.isin.upper() in ident_set) or 
               (t.ticker and t.ticker.upper() in ident_set) or 
               (t.name and t.name.upper() in ident_set)
        ]
        
        related_tx.sort(key=lambda x: x.date)
        
        balance = 0
        for t in related_tx:
            print(f"  {t.date.date()} [{t.type.value}] {t.shares} @ {t.price} ({t.ticker}/{t.isin}) - {t.name}")
            if t.type == TransactionType.BUY:
                balance += t.shares
            elif t.type == TransactionType.SELL:
                balance -= t.shares
        
        print(f"  -> Raw CSV Balance: {balance}")

        # Check Splits (CRITICAL: Filter out future-dated splits)
        if related_tx:
            ticker = related_tx[0].ticker or related_tx[0].isin
            all_splits = CorporateActionService.fetch_split_history(ticker)
            # Filter to exclude future splits that corrupt holdings
            from datetime import datetime
            today = datetime.now().date()
            splits = [s for s in all_splits if s.action_date <= today]
            future_splits = [s for s in all_splits if s.action_date > today]
            
            print(f"  -> Detected Splits: {[f'{s.action_date}: {s.ratio_to/s.ratio_from}x' for s in splits]}")
            if future_splits:
                print(f"  -> Future Splits (IGNORED): {[f'{s.action_date}: {s.ratio_to/s.ratio_from}x' for s in future_splits]}")

    print("\n" + "="*50)
    print("HOLDINGS DISCREPANCY ANALYSIS")
    print("="*50)
    
    # Build Portfolio to see what gets filtered
    pf = Portfolio(transactions)
    # pf.process_transaction was removed in favor of constructor logic, or we iterate if we want to trace steps
    # But Portfolio(transactions) automatically calls internal processing.
        
    holdings = pf.holdings  # Dict[ticker, Position] accessed as attribute
    
    active = [h for h in holdings.values() if h.shares > 0.0001]
    print(f"Portfolio Calculator found {len(active)} active holdings.")
    
    # Check for "Stock" vs "Option"
    options = [h for h in active if h.asset_type == AssetType.OPTION]
    stocks = [h for h in active if h.asset_type == AssetType.STOCK]
    unknown = [h for h in active if h.asset_type == AssetType.UNKNOWN]
    
    print(f"  - Stocks: {len(stocks)}")
    print(f"  - Options: {len(options)}")
    print(f"  - Unknown: {len(unknown)}")
    
    if options:
        print("\n  WARNING: The following consist of 'Options' (Check if these are actually Stocks):")
        for o in options[:5]:
            print(f"    - {o.ticker} ({o.name})")

    if unknown:
        print("\n  WARNING: The following are 'Unknown' type:")
        for u in unknown[:5]:
            print(f"    - {u.ticker} ({u.name})")

if __name__ == "__main__":
    analyze()
