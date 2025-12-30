"""Quick test to verify cost basis fix"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from parsers.csv_parser import CSVParser
from calculators.portfolio import Portfolio
from decimal import Decimal

# Load transactions
file_path = Path(__file__).parent / "Testdata" / "Deine Gesamtansicht-20251229-055109.csv"
with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

parser = CSVParser()
transactions = parser.parse_csv(content)

# Build portfolio
pf = Portfolio(transactions)

# Test specific positions
test_cases = {
    'US64110L1061': {'expected_shares': 25, 'expected_avg': 82.93, 'name': 'Netflix'},
    'DK0062498333': {'expected_shares': 50, 'expected_avg': 41.37, 'name': 'Novo Nordisk'},
    'US48581R2058': {'expected_shares': 76, 'expected_avg': 63.88, 'name': 'Kaspi'},
    'US88160R1014': {'expected_shares': 10, 'expected_avg': 175.14, 'name': 'Tesla'},
}

print("\n" + "="*70)
print("COST BASIS VERIFICATION TEST")
print("="*70)

for ticker, expected in test_cases.items():
    if ticker in pf.holdings:
        pos = pf.holdings[ticker]
        actual_avg = float(pos.cost_basis / pos.shares) if pos.shares > 0 else 0
        shares_match = abs(float(pos.shares) - expected['expected_shares']) < 0.01
        avg_match = abs(actual_avg - expected['expected_avg']) < 0.01
        
        status = "PASS" if (shares_match and avg_match) else "FAIL"
        
        print(f"\n{expected['name']} ({ticker}):")
        print(f"  Shares: {pos.shares} (expected {expected['expected_shares']}) {'OK' if shares_match else 'FAIL'}")
        print(f"  Avg Cost: EUR{actual_avg:.2f} (expected EUR{expected['expected_avg']}) {'OK' if avg_match else 'FAIL'}")
        print(f"  Status: {status}")
        
        if not avg_match:
            print(f"  Difference: €{actual_avg - expected['expected_avg']:.2f}")
    else:
        print(f"\n{expected['name']} ({ticker}): ❌ NOT FOUND")

print("\n" + "="*70)
