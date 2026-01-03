"""
Test script for ticker normalization and market data optimizations.
"""

import sys
import io
sys.path.insert(0, r'c:\Users\Andre\PycharmProjects\PortfolioViewer')

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from lib.market_data import normalize_ticker

# Test Cases
test_cases = [
    ("BRK/B", "BRK-B"),
    ("BRK.B", "BRK-B"),
    ("brk/b", "BRK-B"),
    ("BF/A", "BF-A"),
    ("AAPL", "AAPL"),
    ("NOVO-B.CO", "NOVO-B.CO"),
    ("", ""),
    (None, None),
]

print("=" * 60)
print("TICKER NORMALIZATION TESTS")
print("=" * 60)

all_passed = True
for input_ticker, expected_output in test_cases:
    result = normalize_ticker(input_ticker)
    passed = result == expected_output
    status = "✓ PASS" if passed else "✗ FAIL"
    
    if not passed:
        all_passed = False
        print(f"{status}: '{input_ticker}' -> '{result}' (expected: '{expected_output}')")
    else:
        print(f"{status}: '{input_ticker}' -> '{result}'")

print("=" * 60)
if all_passed:
    print("ALL TESTS PASSED ✓")
else:
    print("SOME TESTS FAILED ✗")
    sys.exit(1)

# Test currency caching
print("\n" * 2)
print("=" * 60)
print("CURRENCY DETECTION & CACHING TEST")
print("=" * 60)

from lib.market_data import get_currency_for_ticker

test_tickers = [
    ("AAPL", "USD"),
    ("NOVO-B.CO", "DKK"),
    ("ASML.AS", "EUR"),
    ("BRK-B", "USD"),
]

for ticker, expected_currency in test_tickers:
    currency = get_currency_for_ticker(ticker)
    status = "✓" if currency == expected_currency else "✗"
    print(f"{status} {ticker}: {currency} (expected: {expected_currency})")

print("=" * 60)
print("Tests complete. Check logs above for any issues.")
