"""Full test across all 41 positions"""

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

# All 41 expected positions from user's list
expected_positions = {
    'IE000716YHJ7': {'shares': 5350, 'avg': 7.01, 'name': 'Invesco FTSE All-World'},
    'US83406F1021': {'shares': 490, 'avg': 7.49, 'name': 'SoFi Technologies'},
    'US4330001060': {'shares': 315, 'avg': 14.91, 'name': 'Hims & Hers Health'},
    'KYG6683N1034': {'shares': 476.64, 'avg': 11.36, 'name': 'Nubank'},
    'US48581R2058': {'shares': 76, 'avg': 63.88, 'name': 'Kaspi.kz'},
    'US02079K3059': {'shares': 17, 'avg': 151.51, 'name': 'Alphabet A'},
    'US88160R1014': {'shares': 10, 'avg': 175.14, 'name': 'Tesla'},
    'NL0010273215': {'shares': 4.08, 'avg': 724.93, 'name': 'ASML Holding'},
    'US89377M1099': {'shares': 34, 'avg': 75.50, 'name': 'TRANSMEDICS GROUP'},
    'US0231351067': {'shares': 17, 'avg': 184.60, 'name': 'Amazon'},
    'DK0010272202': {'shares': 12, 'avg': 204.63, 'name': 'Genmab'},
    'US67066G1040': {'shares': 19, 'avg': 89.64, 'name': 'NVIDIA'},
    'US5949181045': {'shares': 7, 'avg': 394.76, 'name': 'Microsoft'},
    'US8740391003': {'shares': 10, 'avg': 145.23, 'name': 'TSMC (ADR)'},
    'DK0062498333': {'shares': 50, 'avg': 41.37, 'name': 'Novo Nordisk B'},
    'LU2290522684': {'shares': 200.84, 'avg': 9.77, 'name': 'InPost'},
    'US64110L1061': {'shares': 25, 'avg': 82.93, 'name': 'Netflix'},
    'US0404132054': {'shares': 16, 'avg': 64.03, 'name': 'Arista Networks'},
    'IE000S9YS762': {'shares': 5, 'avg': 339.29, 'name': 'Linde'},
    'US98419M1009': {'shares': 15, 'avg': 119.18, 'name': 'XYLEM'},
    'US58733R1023': {'shares': 1, 'avg': 1769.70, 'name': 'Mercado Libre'},
    'US98978V1035': {'shares': 15, 'avg': 99.94, 'name': 'Zoetis'},
    'US81141R1005': {'shares': 14, 'avg': 68.76, 'name': 'Sea (ADR)'},
    'US7707001027': {'shares': 15, 'avg': 17.66, 'name': 'Robinhood'},
    'NL0000687663': {'shares': 12, 'avg': 103.25, 'name': 'AerCap'},
    'KYG9830T1067': {'shares': 350, 'avg': 4.71, 'name': 'Xiaomi'},
    'KYG4124C1096': {'shares': 322, 'avg': 4.38, 'name': 'Grab Holdings'},
    'US26856L1035': {'shares': 20, 'avg': 71.72, 'name': 'E.L.F. BEAUTY'},
    'CA1363751027': {'shares': 16, 'avg': 83.09, 'name': 'Canadian National Railway'},
    'US45841N1072': {'shares': 24, 'avg': 27.67, 'name': 'Interactive Brokers'},
    'NL0006294274': {'shares': 10, 'avg': 98.91, 'name': 'Euronext'},
    'US15118V2079': {'shares': 30, 'avg': 37.58, 'name': 'Celsius Holdings'},
    'US63253R2013': {'shares': 24, 'avg': 36.66, 'name': 'NAC Kazatomprom'},
    'US0304201033': {'shares': 10, 'avg': 111.13, 'name': 'American Water Works'},
    'LU3176111881': {'shares': 10.1, 'avg': 100.00, 'name': 'EQT Nexus Fund'},
    'US55354G1004': {'shares': 2, 'avg': 464.45, 'name': 'MSCI'},
    'GRS469003024': {'shares': 40, 'avg': 15.15, 'name': 'Kri-Kri'},
    'CA11271J1075': {'shares': 20, 'avg': 39.67, 'name': 'Brookfield Corp'},
    'AT0000A0E9W5': {'shares': 27, 'avg': 17.86, 'name': 'Kontron'},
    'PLDINPL00011': {'shares': 60, 'avg': 7.59, 'name': 'Dino Polska'},
    'US30303M1027': {'shares': 1, 'avg': 473.20, 'name': 'Meta Platforms'},
}

print("\n" + "="*90)
print("FULL PORTFOLIO COST BASIS VERIFICATION - 41 POSITIONS")
print("="*90)

perfect_matches = 0
close_matches = 0
significant_diff = 0
not_found = 0

results = []

for ticker, expected in expected_positions.items():
    if ticker in pf.holdings:
        pos = pf.holdings[ticker]
        actual_avg = float(pos.cost_basis / pos.shares) if pos.shares > 0 else 0
        shares_match = abs(float(pos.shares) - expected['shares']) < 0.1
        
        # Calculate difference
        diff = actual_avg - expected['avg']
        diff_pct = (diff / expected['avg'] * 100) if expected['avg'] > 0 else 0
        
        # Categorize
        if abs(diff) < 0.01:
            status = "PERFECT"
            perfect_matches += 1
        elif abs(diff) < 1.00:
            status = "CLOSE"
            close_matches += 1
        else:
            status = "DIFF"
            significant_diff += 1
        
        results.append({
            'ticker': ticker,
            'name': expected['name'],
            'expected_avg': expected['avg'],
            'actual_avg': actual_avg,
            'diff': diff,
            'diff_pct': diff_pct,
            'shares_ok': shares_match,
            'status': status
        })
    else:
        not_found += 1
        results.append({
            'ticker': ticker,
            'name': expected['name'],
            'expected_avg': expected['avg'],
            'actual_avg': 0,
            'diff': 0,
            'diff_pct': 0,
            'shares_ok': False,
            'status': 'NOT_FOUND'
        })

# Sort by status then by difference
status_order = {'PERFECT': 0, 'CLOSE': 1, 'DIFF': 2, 'NOT_FOUND': 3}
results.sort(key=lambda x: (status_order[x['status']], abs(x['diff']), x['name']))

# Print results
print(f"\n{'Position':<30} {'Expected':>10} {'Actual':>10} {'Diff':>10} {'Diff%':>8} {'Status':>10}")
print("-" * 90)

for r in results:
    name = r['name'][:28]
    print(f"{name:<30} EUR{r['expected_avg']:>8.2f} EUR{r['actual_avg']:>8.2f} "
          f"EUR{r['diff']:>8.2f} {r['diff_pct']:>7.1f}% {r['status']:>10}")

print("\n" + "="*90)
print("SUMMARY STATISTICS")
print("="*90)
print(f"Total Positions:        {len(expected_positions)}")
print(f"Perfect Match (<0.01):  {perfect_matches} ({perfect_matches/len(expected_positions)*100:.1f}%)")
print(f"Close Match (<1.00):    {close_matches} ({close_matches/len(expected_positions)*100:.1f}%)")
print(f"Significant Diff (>1):  {significant_diff} ({significant_diff/len(expected_positions)*100:.1f}%)")
print(f"Not Found:              {not_found}")
print("="*90)

# Show top 5 differences
print("\nTOP 5 DISCREPANCIES:")
print("-" * 90)
diff_results = [r for r in results if r['status'] not in ['NOT_FOUND', 'PERFECT']]
diff_results.sort(key=lambda x: abs(x['diff']), reverse=True)

for r in diff_results[:5]:
    print(f"{r['name']:<30} Expected: EUR{r['expected_avg']:>8.2f}, "
          f"Actual: EUR{r['actual_avg']:>8.2f}, Diff: EUR{r['diff']:>8.2f}")

print("\n" + "="*90)
