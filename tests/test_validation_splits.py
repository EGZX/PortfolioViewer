"""
Quick test of enhanced validation with fixed time-based logic

Copyright (c) 2026 Andre. All rights reserved.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from lib.validators import DataValidator

# Test scenario: Growth stock held for years
validator = DataValidator()

transactions = [
    # Normal growth: 100 -> 500 over 10 years (should NOT flag)
    Transaction(
        date=datetime(2014, 1, 1),
        type=TransactionType.BUY,
        ticker="NVDA",
        shares=Decimal("100"),
        price=Decimal("20.00"),
        total=Decimal("-2000"),
        currency="USD"
    ),
    Transaction(
        date=datetime(2024, 1, 1),
        type=TransactionType.SELL,
        ticker="NVDA",
        shares=Decimal("50"),
        price=Decimal("500.00"),  # 25x gain over 10 years - NORMAL!
        total=Decimal("25000"),
        currency="USD"
    ),
    
    # Sudden drop: 150 -> 75 in 1 day (SHOULD flag - likely 2-for-1 split)
    Transaction(
        date=datetime(2020, 8, 1),
        type=TransactionType.BUY,
        ticker="AAPL",
        shares=Decimal("10"),
        price=Decimal("100.00"),
        total=Decimal("-1000"),
        currency="USD"
    ),
    Transaction(
        date=datetime(2020, 8, 2),  # Next day!
        type=TransactionType.BUY,
        ticker="AAPL",
        shares=Decimal("10"),
        price=Decimal("50.00"),  # 50% drop overnight - SPLIT!
        total=Decimal("-500"),
        currency="USD"
    ),
]

issues = validator.validate_all(transactions)

print("=" * 70)
print("VALIDATION TEST RESULTS")
print("=" * 70)
print(f"Total issues: {len(issues)}\n")

for issue in issues:
    print(f"[{issue.severity}] {issue.category}")
    print(f"  {issue.message}\n")

print("=" * 70)
print("EXPECTED:")
print("  - NO flag for NVDA (10-year gap)")
print("  - FLAG for AAPL (1-day gap, 50% drop)")
print("=" * 70)
