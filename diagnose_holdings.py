"""
Portfolio Holdings Diagnostic Script

This script analyzes the CSV to show:
1. Total unique ISINs in the CSV
2. Current non-zero holdings by ISIN
3. Comparison with what the app is showing (32 positions)
"""

import pandas as pd
from collections import defaultdict
from decimal import Decimal
from datetime import datetime

def analyze_csv(csv_path):
    """Analyze CSV to find current holdings."""
    
    # Read CSV
    df = pd.read_csv(csv_path, delimiter=';', decimal=',')
    
    print("=" * 80)
    print("PORTFOLIO HOLDINGS DIAGNOSTIC")
    print("=" * 80)
    print()
    
    print(f"Total transactions in CSV: {len(df)}")
    print(f"Total unique ISINs: {df['Identifier'].nunique()}")
    print()
    
    # Calculate current holdings manually
    holdings = defaultdict(lambda: {'shares': Decimal(0), 'transactions': []})
    
    for idx, row in df.iterrows():
        isin = row['Identifier']
        tx_type = row['Type']
        shares = Decimal(str(row.get('Shares', 0)).replace(',', '.'))
        name = row.get('HoldingName', 'Unknown')
        date = row.get('DateTime', 'Unknown')
        broker = row.get('Broker', 'Unknown')
        
        # Track transaction
        holdings[isin]['transactions'].append({
            'date': date,
            'type': tx_type,
            'shares': shares,
            'broker': broker
        })
        
        # Update shares
        if tx_type in ['TransferIn', 'Buy']:
            holdings[isin]['shares'] += shares
            holdings[isin]['name'] = name
        elif tx_type in ['TransferOut', 'Sell']:
            holdings[isin]['shares'] -= shares
            holdings[isin]['name'] = name
    
    # Filter to non-zero holdings
    active_holdings = {k: v for k, v in holdings.items() if v['shares'] > 0}
    zero_holdings = {k: v for k, v in holdings.items() if v['shares'] == 0}
    
    print(f"Active holdings (shares > 0): {len(active_holdings)}")
    print(f"Sold positions (shares = 0): {len(zero_holdings)}")
    print()
    
    # Show specific ticker the user mentioned
    test_isin = 'US64110L1061'
    print(f"Checking specific ticker: {test_isin}")
    if test_isin in holdings:
        print(f"  Current shares: {holdings[test_isin]['shares']}")
        print(f"  Name: {holdings[test_isin].get('name', 'Unknown')}")
        print(f"  Total transactions: {len(holdings[test_isin]['transactions'])}")
        print(f"  Brokers used: {set(t['broker'] for t in holdings[test_isin]['transactions'])}")
        print()
    else:
        print(f"  ⚠️ NOT FOUND in CSV!")
        print()
    
    # Check Cliq Digital (should be sold)
    cliq_isin = 'DE000A0HHJR3'
    print(f"Checking Cliq Digital: {cliq_isin}")
    if cliq_isin in holdings:
        print(f"  Current shares: {holdings[cliq_isin]['shares']}")
        print(f"  Name: {holdings[cliq_isin].get('name', 'Unknown')}")
        if holdings[cliq_isin]['shares'] == 0:
            print(f"  ✅ Correctly shows as FULLY SOLD")
        else:
            print(f"  ⚠️ ERROR: Should be sold but shows {holdings[cliq_isin]['shares']} shares")
        print()
    
    # Show all active holdings
    print("=" * 80)
    print(f"ALL ACTIVE HOLDINGS ({len(active_holdings)} total):")
    print("=" * 80)
    for isin, data in sorted(active_holdings.items(), key=lambda x: x[1]['shares'], reverse=True):
        name = data.get('name', 'Unknown')
        shares = data['shares']
        brokers = set(t['broker'] for t in data['transactions'])
        print(f"{isin:15} | {shares:>10} shares | {name[:40]:40} | Brokers: {', '.join(brokers)}")
    
    print()
    print("=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Expected active positions: {len(active_holdings)}")
    print(f"App shows: 32 positions")
    print(f"Difference: {len(active_holdings) - 32} positions missing")
    print()
    
    # Check broker distribution
    all_brokers = set()
    for data in holdings.values():
        for tx in data['transactions']:
            all_brokers.add(tx['broker'])
    
    print(f"Brokers found in CSV: {', '.join(sorted(all_brokers))}")
    print()
    
    print("Recommendation:")
    if len(active_holdings) > 32:
        print("  - Check if the app is filtering transactions by broker")
        print("  - Verify all transactions are being parsed from the CSV")
        print("  - Look for any hidden filters in portfolio_viewer.py")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python diagnose_holdings.py <path_to_csv>")
        sys.exit(1)
    
    analyze_csv(sys.argv[1])
