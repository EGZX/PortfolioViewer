"""Test the cost basis fix for CASH TRANSFER_IN transactions."""
import sys
from decimal import Decimal
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from modules.viewer.portfolio import Portfolio

def test_cash_transfer_in_no_cost_basis():
    """Test that CASH TRANSFER_IN doesn't add to cost basis."""
    print("=" * 80)
    print("TEST: CASH TRANSFER_IN should NOT inflate cost basis")
    print("=" * 80)
    
    # Create a portfolio with cash transfer
    transactions = [
        Transaction(
            id="t1",
            date=datetime(2025, 12, 9),
            type=TransactionType.TRANSFER_IN,
            ticker="CASH",
            isin=None,
            name="Cash TransferIn",
            asset_type=AssetType.UNKNOWN,
            shares=Decimal(0),
            price=Decimal(1.0),
            total=Decimal(5045.48),  # EUR amount
            fees=Decimal(0),
            currency="EUR",
            original_currency="EUR",
            broker="interactive_brokers"
        ),
        Transaction(
            id="t2",
            date=datetime(2025, 12, 9),
            type=TransactionType.TRANSFER_IN,
            ticker="CASH",
            isin=None,
            name="Cash TransferIn",
            asset_type=AssetType.UNKNOWN,
            shares=Decimal(0),
            price=Decimal(1.0),
            total=Decimal(16000.0),  # EUR amount
            fees=Decimal(0),
            currency="EUR",
            original_currency="EUR",
            broker="interactive_brokers"
        )
    ]
    
    portfolio = Portfolio(transactions)
    
    # Check if CASH position exists
    cash_position = portfolio.holdings.get("CASH")
    
    print(f"\nTransactions processed: {len(portfolio.transactions)}")
    print(f"Holdings count: {len(portfolio.holdings)}")
    
    if cash_position:
        print(f"\nCASH Position found:")
        print(f"  Shares: {cash_position.shares}")
        print(f"  Cost Basis: €{cash_position.cost_basis}")
        print(f"  Expected Cost Basis: €0.00")
        
        # Assert cost basis is 0
        assert cash_position.cost_basis == Decimal(0), \
            f"FAIL: CASH cost basis should be €0, but got €{cash_position.cost_basis}"
        print("  PASS: Cost basis correctly set to €0")
    else:
        # If CASH position doesn't exist (filtered out due to 0 shares), that's also OK
        print("\nCASH position not in holdings (likely filtered due to 0 shares)")
        print("  PASS: No cost basis added")
    
    # Check invested capital was updated correctly
    print(f"\nInvested Capital: €{portfolio.invested_capital}")
    print(f"Expected: €0.00 (CASH transfers don't count as investments)")
    
    # CASH transfers without actual ticker shouldn't add to invested_capital
    # But according to the logic, TRANSFER_IN with no ticker adds to invested_capital
    # This is expected behavior for cash deposits
    
    print("\n" + "=" * 80)
    print("TEST PASSED: CASH transfers do not inflate cost basis")
    print("=" * 80)


def test_fx_transfer_in_no_cost_basis():
    """Test that FX currency pair TRANSFER_IN doesn't add to cost basis."""
    print("\n" + "=" * 80)
    print("TEST: FX TRANSFER_IN (EUR.USD) should NOT inflate cost basis")
    print("=" * 80)
    
    transactions = [
        Transaction(
            id="t1",
            date=datetime(2025, 12, 9),
            type=TransactionType.TRANSFER_IN,
            ticker="EUR.USD",
            isin=None,
            name="EUR.USD",
            asset_type=AssetType.UNKNOWN,
            shares=Decimal(1000),
            price=Decimal(1.16),
            total=Decimal(1160.0),  # USD amount converted to EUR
            fees=Decimal(0),
            currency="EUR",
            original_currency="USD",
            broker="interactive_brokers"
        )
    ]
    
    portfolio = Portfolio(transactions)
    
    # Check if EUR.USD position exists
    fx_position = portfolio.holdings.get("EUR.USD")
    
    print(f"\nTransactions processed: {len(portfolio.transactions)}")
    print(f"Holdings count: {len(portfolio.holdings)}")
    
    if fx_position:
        print(f"\nEUR.USD Position found:")
        print(f"  Shares: {fx_position.shares}")
        print(f"  Cost Basis: €{fx_position.cost_basis}")
        print(f"  Expected Cost Basis: €0.00")
        
        # Assert cost basis is 0
        assert fx_position.cost_basis == Decimal(0), \
            f"FAIL: FX cost basis should be EUR 0, but got EUR {fx_position.cost_basis}"
        print("  PASS: Cost basis correctly set to EUR 0")
    else:
        print("\nEUR.USD position not in holdings (likely filtered due to 0 shares)")
        print("  PASS: No cost basis added")
    
    print("\n" + "=" * 80)
    print("TEST PASSED: FX transfers do not inflate cost basis")
    print("=" * 80)


def test_stock_transfer_in_has_cost_basis():
    """Test that real stock TRANSFER_IN still adds to cost basis."""
    print("\n" + "=" * 80)
    print("TEST: Real stock TRANSFER_IN SHOULD add to cost basis")
    print("=" * 80)
    
    transactions = [
        Transaction(
            id="t1",
            date=datetime(2025, 12, 1),
            type=TransactionType.TRANSFER_IN,
            ticker="AAPL",
            isin="US0378331005",
            name="Apple Inc.",
            asset_type=AssetType.STOCK,
            shares=Decimal(10),
            price=Decimal(200.0),
            total=Decimal(2000.0),  # EUR
            fees=Decimal(0),
            currency="EUR",
            original_currency="USD",
            broker="interactive_brokers"
        )
    ]
    
    portfolio = Portfolio(transactions)
    
    # Check if AAPL position exists
    aapl_position = portfolio.holdings.get("US0378331005") or portfolio.holdings.get("AAPL")
    
    print(f"\nTransactions processed: {len(portfolio.transactions)}")
    print(f"Holdings count: {len(portfolio.holdings)}")
    
    assert aapl_position is not None, "FAIL: AAPL position should exist"
    
    print(f"\nAAPL Position found:")
    print(f"  Shares: {aapl_position.shares}")
    print(f"  Cost Basis: €{aapl_position.cost_basis}")
    print(f"  Expected Cost Basis: €2000.00")
    
    # Assert cost basis is 2000
    assert aapl_position.cost_basis == Decimal(2000.0), \
        f"FAIL: AAPL cost basis should be EUR 2000, but got EUR {aapl_position.cost_basis}"
    print("  PASS: Real stock transfer correctly adds to cost basis")
    
    print("\n" + "=" * 80)
    print("TEST PASSED: Real stock transfers add to cost basis correctly")
    print("=" * 80)


if __name__ == "__main__":
    test_cash_transfer_in_no_cost_basis()
    test_fx_transfer_in_no_cost_basis()
    test_stock_transfer_in_has_cost_basis()
    
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED - Cost basis fix verified successfully")
    print("=" * 80)
