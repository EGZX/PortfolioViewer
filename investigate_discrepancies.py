"""Investigate all discrepancies"""

import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent))

from parsers.csv_parser import CSVParser
from calculators.portfolio import Portfolio
from decimal import Decimal

# Load CSV directly
file_path = Path(__file__).parent / "Testdata" / "Deine Gesamtansicht-20251229-055109.csv"
df = pd.read_csv(file_path, delimiter=';', decimal=',')

# Positions with significant discrepancies
investigate = {
    'US45841N1072': {'name': 'Interactive Brokers', 'expected': 27.67, 'actual': 110.67, 'diff': 83.00},
    'US67066G1040': {'name': 'NVIDIA', 'expected': 89.64, 'actual': 170.31, 'diff': 80.67},
    'PLDINPL00011': {'name': 'Dino Polska', 'expected': 7.59, 'actual': 75.86, 'diff': 68.27},
    'US30303M1027': {'name': 'Meta Platforms', 'expected': 473.20, 'actual': 495.59, 'diff': 22.39},
    'US88160R1014': {'name': 'Tesla', 'expected': 175.14, 'actual': 186.18, 'diff': 11.04},
    'US26856L1035': {'name': 'E.L.F. BEAUTY', 'expected': 71.72, 'actual': 79.96, 'diff': 8.24},
    'US8740391003': {'name': 'TSMC', 'expected': 145.23, 'actual': 152.33, 'diff': 7.10},
    'US81141R1005': {'name': 'Sea ADR', 'expected': 68.76, 'actual': 72.51, 'diff': 3.75},
    'NL0006294274': {'name': 'Euronext', 'expected': 98.91, 'actual': 101.07, 'diff': 2.16},
    'US02079K3059': {'name': 'Alphabet A', 'expected': 151.51, 'actual': 149.92, 'diff': -1.59},
}

print("\n" + "="*90)
print("DISCREPANCY INVESTIGATION - TRANSACTION ANALYSIS")
print("="*90)

for ticker, info in investigate.items():
    txns = df[df['identifier'] == ticker].copy()
    
    if len(txns) == 0:
        print(f"\n{info['name']} ({ticker}): NO TRANSACTIONS FOUND")
        continue
    
    print(f"\n{info['name']} ({ticker}):")
    print(f"  Expected: EUR{info['expected']:.2f} | Actual: EUR{info['actual']:.2f} | Diff: EUR{info['diff']:.2f}")
    print(f"  Total Transactions: {len(txns)}")
    
    # Count by type
    buy_count = len(txns[txns['type'] == 'Buy'])
    sell_count = len(txns[txns['type'] == 'Sell'])
    other = len(txns) - buy_count - sell_count
    
    print(f"  Buys: {buy_count}, Sells: {sell_count}, Other: {other}")
    
    # Show first 3 and last 3 transactions
    txns_sorted = txns.sort_values('date')
    print(f"\n  First 3 transactions:")
    for idx, row in txns_sorted.head(3).iterrows():
        print(f"    {row['date']}: {row['type']} {row['shares']} @ EUR{row['price']:.2f}")
    
    if len(txns) > 6:
        print(f"  ... ({len(txns) - 6} more) ...")
    
    if len(txns) > 3:
        print(f"  Last 3 transactions:")
        for idx, row in txns_sorted.tail(3).iterrows():
            print(f"    {row['date']}: {row['type']} {row['shares']} @ EUR{row['price']:.2f}")
    
    # Calculate simple average of buy prices
    buys = txns[txns['type'] == 'Buy']
    if len(buys) > 0:
        total_shares = buys['shares'].sum()
        total_cost = (buys['shares'] * buys['price']).sum()
        simple_avg = total_cost / total_shares if total_shares > 0 else 0
        print(f"\n  Simple avg of ALL buys: EUR{simple_avg:.2f}")
        print(f"  Difference from expected: EUR{simple_avg - info['expected']:.2f}")
        print(f"  Difference from actual (moving avg): EUR{simple_avg - info['actual']:.2f}")

print("\n" + "="*90)
print("\nKEY INSIGHTS:")
print("="*90)
print("""
1. If simple buy average >> moving average:
   → Likely old cheaper shares were sold, moving average is lower

2. If simple buy average << moving average:  
   → Unusual, check for data issues

3. If huge difference (300%+):
   → Likely STOCK SPLIT not reflected in broker's reported entry price
   → Broker shows pre-split price, we calculate post-split

4. If small difference (<10%):
   → Different accounting methods (FIFO vs Moving Average)
   → Fee handling differences
""")
print("="*90)
