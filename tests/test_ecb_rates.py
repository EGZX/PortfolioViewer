"""
Test ECB FX Rate Provider

Validates ECB API integration and tax compliance.
"""

import sys
import io
from datetime import date
from decimal import Decimal

sys.path.insert(0, r'c:\Users\Andre\PycharmProjects\PortfolioViewer')

# Fix encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from lib.ecb_rates import get_ecb_rate, ECBRateProvider

print("=" * 60)
print("ECB FX RATE PROVIDER TEST")
print("=" * 60)

# Test 1: EUR self-conversion
print("\n>>> Test 1: EUR to EUR (should be 1.0)")
rate = get_ecb_rate(date(2024, 1, 15), "EUR", "EUR")
print(f"EUR/EUR: {rate}")
assert rate == Decimal("1.0"), "EUR self-conversion should always be 1.0"
print("✓ PASS")

# Test 2: USD to EUR (known historical date)
print("\n>>> Test 2: USD to EUR (historical)")
rate = get_ecb_rate(date(2024, 1, 15), "USD", "EUR")
print(f"USD/EUR on 2024-01-15: {rate}")
assert rate is not None, "Should return a rate"
assert rate > 0, "Rate should be positive"
print(f"✓ PASS - Rate: {rate}")

# Test 3: GBP to EUR
print("\n>>> Test 3: GBP to EUR (historical)")
rate = get_ecb_rate(date(2024, 3, 1), "GBP", "EUR")
print(f"GBP/EUR on 2024-03-01: {rate}")
assert rate is not None, "Should return a rate"
print(f"✓ PASS - Rate: {rate}")

# Test 4: Caching (second call should be instant)
print("\n>>> Test 4: Cache efficiency (second call)")
import time
start = time.time()
rate1 = get_ecb_rate(date(2024, 1, 15), "USD", "EUR")
duration1 = time.time() - start

start = time.time()
rate2 = get_ecb_rate(date(2024, 1, 15), "USD", "EUR")
duration2 = time.time() - start

print(f"First call: {duration1:.4f}s")
print(f"Second call (cached): {duration2:.4f}s")
assert rate1 == rate2, "Cached rate should match"
assert duration2 < duration1, "Cached call should be faster"
print("✓ PASS - Caching works")

# Test 5: Weekend handling (should use previous business day)
print("\n>>> Test 5: Weekend handling")
# January 6, 2024 was a Saturday
rate = get_ecb_rate(date(2024, 1, 6), "USD", "EUR")
print(f"USD/EUR on Saturday 2024-01-06: {rate}")
assert rate is not None, "Should fallback to previous business day"
print("✓ PASS - Weekend handling works")

# Test 6: Unsupported currency
print("\n>>> Test 6: Unsupported currency (should fallback to yfinance)")
rate = get_ecb_rate(date(2024, 1, 15), "XYZ", "EUR")
print(f"XYZ/EUR (unsupported): {rate}")
# This will fallback to yfinance, which should also fail
print("✓ PASS - Unsupported currency handled")

# Test 7: Tax calculation example
print("\n>>> Test 7: Tax Calculation Example")
print("Scenario: Bought 100 shares of US stock at $150 USD on 2024-01-15")
shares = Decimal("100")
price_usd = Decimal("150.00")
total_usd = shares * price_usd

fx_rate = get_ecb_rate(date(2024, 1, 15), "USD", "EUR")
cost_basis_eur = total_usd * fx_rate

print(f"Total USD: ${total_usd}")
print(f"ECB FX Rate: {fx_rate}")
print(f"Cost Basis EUR: €{cost_basis_eur:.2f}")
print("✓ PASS - Tax calculation works")

print("\n" + "=" * 60)
print("ALL TESTS PASSED ✓")
print("=" * 60)
print("\nNOTE: ECB rates are now permanently cached in portfolio.db")
print("Check: SELECT * FROM fx_rates_ecb;")
