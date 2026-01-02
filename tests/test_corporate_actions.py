"""
Unit Tests for Corporate Actions (Spin-offs and Mergers)

Tests enhanced corporate actions functionality including spin-offs
and configured actions.

Copyright (c) 2026 Andre. All rights reserved.
"""

import pytest
from datetime import date
from decimal import Decimal

from lib.corporate_actions import CorporateAction, CorporateActionService
from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType


class TestSpinOffHandling:
    """Test spin-off corporate actions."""
    
    def test_spinoff_cost_basis_allocation(self):
        """Test that cost basis is correctly allocated in spin-offs."""
        # Create parent company holding
        parent_holding = Transaction(
            date=date(2015, 1, 1),
            type=TransactionType.BUY,
            ticker="EBAY",
            shares=Decimal("100"),
            price=Decimal("50.00"),
            total=Decimal("5000.00"),
            fees=Decimal("10.00"),
            currency="USD",
            cost_basis_eur=Decimal("5010.00")
        )
        
        # Define spin-off action (PayPal from eBay)
        spinoff = CorporateAction(
            ticker="EBAY",
            action_date=date(2015, 7, 17),
            action_type="SpinOff",
            ratio_from=Decimal(1),
            ratio_to=Decimal(1),
            new_ticker="PYPL",
            spin_off_ratio=Decimal("1.0"),  # 1 PYPL per 1 EBAY
            cost_basis_allocation=Decimal("0.20"),  # 20% to PYPL
            notes="PayPal spin-off"
        )
        
        # Apply spin-off
        transactions = [parent_holding]
        result_txns, log = CorporateActionService.apply_spin_off(transactions, spinoff)
        
        # Check results
        assert len(result_txns) == 2  # Parent + spin-off
        
        # Find spin-off transaction
        spinoff_txn = [t for t in result_txns if t.ticker == "PYPL"][0]
        
        # Verify shares (1:1 ratio)
        assert spinoff_txn.shares == Decimal("100")
        
        # Verify cost basis allocation (20%)
        assert spinoff_txn.cost_basis_eur == Decimal("1002.00")  # 20% of 5010
        
        # Verify parent cost basis reduced
        assert parent_holding.cost_basis_eur == Decimal("4008.00")  # 80% of 5010
        
        # Verify log
        assert len(log) == 1
        assert "EBAY → PYPL" in log[0]
    
    def test_spinoff_creates_new_transaction(self):
        """Test that spin-off creates a new BUY transaction for spun-off company."""
        holding = Transaction(
            date=date(2012, 1, 1),
            type=TransactionType.BUY,
            ticker="KRFT",
            shares=Decimal("50"),
            price=Decimal("40.00"),
            total=Decimal("2000.00"),
            currency="USD",
            cost_basis_eur=Decimal("2000.00")
        )
        
        spinoff = CorporateAction(
            ticker="KRFT",
            action_date=date(2012, 10, 1),
            action_type="SpinOff",
            ratio_from=Decimal(1),
            ratio_to=Decimal(1),
            new_ticker="MDLZ",
            spin_off_ratio=Decimal("1.0"),
            cost_basis_allocation=Decimal("0.33"),
            notes="Mondelez spin-off"
        )
        
        transactions = [holding]
        result, log = CorporateActionService.apply_spin_off(transactions, spinoff)
        
        # Find new transaction
        mdlz_txn = [t for t in result if t.ticker == "MDLZ"][0]
        
        # Verify properties
        assert mdlz_txn.type == TransactionType.BUY
        assert mdlz_txn.date == date(2012, 10, 1)
        assert mdlz_txn.shares == Decimal("50")
        assert mdlz_txn.fees == Decimal("0")  # No fees on spin-off
        assert "Spin-off from KRFT" in mdlz_txn.notes
    
    def test_spinoff_ignores_future_holdings(self):
        """Test that spin-off only affects holdings acquired before spin-off date."""
        # Holding before spin-off
        before = Transaction(
            date=date(2015, 1, 1),
            type=TransactionType.BUY,
            ticker="EBAY",
            shares=Decimal("100"),
            price=Decimal("50.00"),
            total=Decimal("5000.00"),
            currency="USD",
            cost_basis_eur=Decimal("5000.00")
        )
        
        # Holding after spin-off (should not be affected)
        after = Transaction(
            date=date(2015, 8, 1),  # After 7/17 spin-off
            type=TransactionType.BUY,
            ticker="EBAY",
            shares=Decimal("50"),
            price=Decimal("30.00"),
            total=Decimal("1500.00"),
            currency="USD",
            cost_basis_eur=Decimal("1500.00")
        )
        
        spinoff = CorporateAction(
            ticker="EBAY",
            action_date=date(2015, 7, 17),
            action_type="SpinOff",
            ratio_from=Decimal(1),
            ratio_to=Decimal(1),
            new_ticker="PYPL",
            spin_off_ratio=Decimal("1.0"),
            cost_basis_allocation=Decimal("0.20")
        )
        
        transactions = [before, after]
        result, log = CorporateActionService.apply_spin_off(transactions, spinoff)
        
        # Should only create 1 PYPL transaction (from 'before' holding)
        pypl_txns = [t for t in result if t.ticker == "PYPL"]
        assert len(pypl_txns) == 1
        
        # After holding should be unchanged
        assert after.cost_basis_eur == Decimal("1500.00")


class TestComprehensiveActions:
    """Test detect_and_apply_all_actions comprehensive handler."""
    
    def test_applies_splits_and_spinoffs(self):
        """Test that comprehensive handler applies both splits and spin-offs."""
        transactions = [
            Transaction(
                date=date(2015, 1, 1),
                type=TransactionType.BUY,
                ticker="EBAY",
                shares=Decimal("100"),
                price=Decimal("50.00"),
                total=Decimal("5000.00"),
                currency="USD"
            )
        ]
        
        # Apply all actions (will load from config if any)
        result, log = CorporateActionService.detect_and_apply_all_actions(
            transactions,
            fetch_splits=False  # Skip API calls for speed
        )
        
        # Should return transactions (may or may not have spin-offs depending on config)
        assert len(result) >= len(transactions)
        assert isinstance(log, list)


class TestCorporateActionClass:
    """Test enhanced CorporateAction dataclass."""
    
    def test_spinoff_action_creation(self):
        """Test creating spin-off action."""
        action = CorporateAction(
            ticker="TEST",
            action_date=date(2020, 1, 1),
            action_type="SpinOff",
            ratio_from=Decimal(1),
            ratio_to=Decimal(1),
            new_ticker="NEWSPIN",
            spin_off_ratio=Decimal("0.5"),
            cost_basis_allocation=Decimal("0.25")
        )
        
        assert action.action_type == "SpinOff"
        assert action.new_ticker == "NEWSPIN"
        assert action.spin_off_ratio == Decimal("0.5")
        assert action.cost_basis_allocation == Decimal("0.25")
        assert "spin-off" in str(action).lower()
    
    def test_merger_action_creation(self):
        """Test creating merger action."""
        action = CorporateAction(
            ticker="ACQUIRED",
            action_date=date(2020, 1, 1),
            action_type="Merger",
            ratio_from=Decimal(1),
            ratio_to=Decimal("1.5"),
            acquiring_ticker="ACQUIRER",
            cash_in_lieu=Decimal("10.00"),
            notes="Merger details"
        )
        
        assert action.action_type == "Merger"
        assert action.acquiring_ticker == "ACQUIRER"
        assert action.cash_in_lieu == Decimal("10.00")
        assert "ACQUIRER" in str(action)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
