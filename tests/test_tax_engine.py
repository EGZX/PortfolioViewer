"""
Basic test for Tax Basis Engine

Quick verification that FIFO and Weighted Average calculations work correctly.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import sys
from pathlib import Path
# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from decimal import Decimal
from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from modules.tax.engine import TaxBasisEngine

# Create test transactions
transactions = [
    # Buy 100 shares on Jan 1, 2023 @ $10
    Transaction(
        date=datetime(2023, 1, 1),
        type=TransactionType.BUY,
        ticker="AAPL",
        isin="US0378331005",  # ISIN for Apple
        name="Apple Inc.",
        asset_type=AssetType.STOCK,
        shares=Decimal("100"),
        price=Decimal("10"),
        fees=Decimal("1"),
        total=Decimal("-1001"),  # Negative for outflow
        original_currency="USD",
        fx_rate=Decimal("0.95")  # USD to EUR
    ),
    
    # Buy 50 shares on Feb 1, 2023 @ $12
    Transaction(
        date=datetime(2023, 2, 1),
        type=TransactionType.BUY,
        ticker="AAPL",
        isin="US0378331005",
        name="Apple Inc.",
        asset_type=AssetType.STOCK,
        shares=Decimal("50"),
        price=Decimal("12"),
        fees=Decimal("1"),
        total=Decimal("-601"),
        original_currency="USD",
        fx_rate=Decimal("0.95")
    ),
    
    # Sell 120 shares on Mar 1, 2024 @ $15
    Transaction(
        date=datetime(2024, 3, 1),
        type=TransactionType.SELL,
        ticker="AAPL",
        isin="US0378331005",
        name="Apple Inc.",
        asset_type=AssetType.STOCK,
        shares=Decimal("120"),
        price=Decimal("15"),
        fees=Decimal("1"),
        total=Decimal("1799"),  # Positive for inflow
        original_currency="USD",
        fx_rate=Decimal("0.92")
    )
]


def test_fifo():
    """Test FIFO lot matching."""
    print("\n=== FIFO Test ===")
    engine = TaxBasisEngine(transactions, matching_strategy="FIFO")
    engine.process_all_transactions()
    
    events = engine.get_realized_events()
    
    print(f"Generated {len(events)} tax events")
    for event in events:
        print(f"  - Sold {event.quantity_sold} shares")
        print(f"    ISIN: {event.isin}")
        print(f"    Acquired: {event.date_acquired}")
        print(f"    Sold: {event.date_sold}")
        print(f"    Proceeds: €{event.proceeds_base:.2f}")
        print(f"    Cost Basis: €{event.cost_basis_base:.2f}")
        print(f"    Realized Gain: €{event.realized_gain:.2f}")
        print(f"    Holding Period: {event.holding_period_days} days")
        print()
    
    # Verify: Should have 2 events (100 from lot 1, 20 from lot 2)
    assert len(events) == 2, f"Expected 2 events, got {len(events)}"
    assert events[0].quantity_sold == Decimal("100"), "First event should sell 100 shares"
    assert events[1].quantity_sold == Decimal("20"), "Second event should sell 20 shares"
    
    print("[PASS] FIFO test passed!")


def test_weighted_average():
    """Test Weighted Average lot matching."""
    print("\n=== Weighted Average Test ===")
    engine = TaxBasisEngine(transactions, matching_strategy="WeightedAverage")
    engine.process_all_transactions()
    
    events = engine.get_realized_events()
    
    print(f"Generated {len(events)} tax events")
    for event in events:
        print(f"  - Sold {event.quantity_sold} shares")
        print(f"    ISIN: {event.isin}")
        print(f"    Acquired: {event.date_acquired} (earliest lot)")
        print(f"    Sold: {event.date_sold}")
        print(f"    Proceeds: €{event.proceeds_base:.2f}")
        print(f"    Cost Basis: €{event.cost_basis_base:.2f}")
        print(f"    Realized Gain: €{event.realized_gain:.2f}")
        print(f"    Method: {event.lot_matching_method.value}")
        print()
    
    # Verify: Should have 1 event (merged lot)
    assert len(events) == 1, f"Expected 1 event, got {len(events)}"
    assert events[0].quantity_sold == Decimal("120"), "Should sell 120 shares from merged lot"
    assert events[0].lot_matching_method.value == "WeightedAverage"
    
    print("[PASS] Weighted Average test passed!")


if __name__ == "__main__":
    test_fifo()
    test_weighted_average()
    print("\n*** All tests passed! ***")
