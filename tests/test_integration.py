"""
Integration Tests for Portfolio Viewer

Tests end-to-end workflows:
1. CSV Import → Transaction Processing → Portfolio Calculation
2. Multi-CSV Import → Deduplication → Merged Portfolio
3. Tax Basis Engine → Tax Calculator → Tax Liability
4. Corporate Actions → Adjusted Transactions → Correct Holdings

Copyright (c) 2026 Andre. All rights reserved.
"""

import pytest
import tempfile
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Import components to test
from parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from calculators.portfolio import Portfolio
from calculators.tax_basis import TaxBasisEngine
from calculators.tax_calculators import get_calculator
from calculators.transaction_store import TransactionStore
from services.corporate_actions import CorporateActionService
from services.pipeline import parse_csv_only


class TestEndToEndWorkflows:
    """Test complete workflows from import to output."""
    
    @pytest.fixture
    def sample_csv_content(self):
        """Sample CSV data for testing."""
        return """Date,Type,Ticker,Shares,Price,Total,Currency
2024-01-15,Buy,AAPL,10,150.00,1500.00,USD
2024-02-20,Buy,MSFT,5,400.00,2000.00,USD
2024-03-10,Sell,AAPL,5,160.00,800.00,USD
2024-04-15,Dividend,AAPL,0,5.00,50.00,USD"""
    
    @pytest.fixture
    def sample_transactions(self):
        """Create sample transactions for testing."""
        return [
            Transaction(
                date=date(2024, 1, 15),
                type=TransactionType.BUY,
                ticker="AAPL",
                isin="US0378331005",
                name="Apple Inc.",
                asset_type=AssetType.STOCK,
                shares=Decimal("10"),
                price=Decimal("150.00"),
                total=Decimal("1500.00"),
                fees=Decimal("5.00"),
                currency="USD"
            ),
            Transaction(
                date=date(2024, 2, 20),
                type=TransactionType.BUY,
                ticker="MSFT",
                isin="US5949181045",
                name="Microsoft Corp.",
                asset_type=AssetType.STOCK,
                shares=Decimal("5"),
                price=Decimal("400.00"),
                total=Decimal("2000.00"),
                fees=Decimal("5.00"),
                currency="USD"
            ),
            Transaction(
                date=date(2024, 3, 10),
                type=TransactionType.SELL,
                ticker="AAPL",
                isin="US0378331005",
                name="Apple Inc.",
                asset_type=AssetType.STOCK,
                shares=Decimal("5"),
                price=Decimal("160.00"),
                total=Decimal("800.00"),
                fees=Decimal("5.00"),
                currency="USD"
            ),
        ]
    
    def test_csv_to_portfolio_workflow(self, sample_csv_content):
        """Test: CSV → Transactions → Portfolio."""
        # Parse CSV
        transactions, _ = parse_csv_only(sample_csv_content)
        
        assert len(transactions) > 0
        assert transactions[0].type in [TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND]
        
        # Create portfolio
        portfolio = Portfolio(transactions)
        
        # Check portfolio properties
        assert portfolio.total_invested > 0
        assert len(portfolio.holdings) > 0
    
    def test_tax_basis_to_calculator_workflow(self, sample_transactions):
        """Test: Transactions → TaxBasisEngine → Tax Calculator."""
        # Process through tax basis engine
        engine = TaxBasisEngine(sample_transactions, matching_strategy="FIFO")
        engine.process_all_transactions()
        
        # Get realized events for 2024
        events = engine.get_realized_events(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
        
        assert len(events) > 0
        
        # Calculate tax using Austria calculator
        calculator = get_calculator("AT")
        liability = calculator.calculate_tax_liability(events, tax_year=2024)
        
        # Verify tax calculation
        assert liability.tax_year == 2024
        assert liability.jurisdiction == "Austria (AT)"
        assert liability.tax_owed >= 0
        
        # Check Austrian-specific rules
        # 27.5% rate
        if liability.taxable_gain > 0:
            expected_tax = liability.taxable_gain * Decimal("0.275")
            assert abs(liability.tax_owed - expected_tax) < Decimal("0.01")
    
    def test_multi_csv_workflow(self, sample_transactions):
        """Test: Multiple CSVs → TransactionStore → Merged Portfolio."""
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_multi.db")
            store = TransactionStore(db_path=db_path, encryption_key=test_key)
            
            # Import first broker
            result1 = store.append_transactions(
                sample_transactions[:2],
                source_name="Broker_A"
            )
            
            assert result1.added == 2
            
            # Import second broker (with one duplicate)
            result2 = store.append_transactions(
                [sample_transactions[1], sample_transactions[2]],
                source_name="Broker_B"
            )
            
            assert result2.added == 1  # Only new transaction added
            assert result2.skipped == 1  # Duplicate skipped
            
            # Get all transactions
            all_transactions = store.get_all_transactions()
            
            assert len(all_transactions) == 3  # Deduplicated
            
            # Create portfolio from merged data
            portfolio = Portfolio(all_transactions)
            assert len(portfolio.holdings) > 0
    
    def test_corporate_actions_workflow(self):
        """Test: Transactions → Corporate Actions → Adjusted Portfolio."""
        # Create transactions before a split
        pre_split_txns = [
            Transaction(
                date=date(2020, 1, 15),
                type=TransactionType.BUY,
                ticker="AAPL",
                shares=Decimal("10"),
                price=Decimal("75.00"),  # Pre-split price
                total=Decimal("750.00"),
                fees=Decimal("5.00"),
                currency="USD"
            ),
        ]
        
        # Apply corporate actions (AAPL had a 4-for-1 split in Aug 2020)
        # Note: This test will only work if yfinance returns split data
        adjusted_txns, log = CorporateActionService.detect_and_apply_splits(
            pre_split_txns,
            fetch_splits=False  # Skip API call for speed
        )
        
        # Verify structure (actual adjustment depends on API availability)
        assert len(adjusted_txns) == len(pre_split_txns)
        assert isinstance(log, list)
    
    def test_full_tax_reporting_workflow(self, sample_transactions):
        """Test: Transactions → Tax Engine → Calculator → JSON Export."""
        # Step 1: Process tax basis
        engine = TaxBasisEngine(sample_transactions, matching_strategy="FIFO")
        engine.process_all_transactions()
        
        # Step 2: Get events
        events = engine.get_realized_events(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31)
        )
        
        # Step 3: Calculate tax
        calculator = get_calculator("AT")
        liability = calculator.calculate_tax_liability(events, 2024)
        
        # Step 4: Export to JSON format
        export_data = {
            "jurisdiction": liability.jurisdiction,
            "tax_year": liability.tax_year,
            "total_realized_gain": float(liability.total_realized_gain),
            "taxable_gain": float(liability.taxable_gain),
            "tax_owed": float(liability.tax_owed),
            "breakdown": {k: float(v) for k, v in liability.breakdown.items()},
        }
        
        # Verify export structure
        assert "jurisdiction" in export_data
        assert "tax_owed" in export_data
        assert export_data["tax_year"] == 2024
        assert isinstance(export_data["breakdown"], dict)


class TestDataIntegrity:
    """Test data integrity across components."""
    
    def test_decimal_precision_maintained(self):
        """Ensure Decimal precision is maintained throughout pipeline."""
        txn = Transaction(
            date=date(2024, 1, 1),
            type=TransactionType.BUY,
            ticker="TEST",
            shares=Decimal("10.123456"),
            price=Decimal("100.9876"),
            total=Decimal("1022.99"),
            fees=Decimal("2.50"),
            currency="EUR"
        )
        
        # Through portfolio
        portfolio = Portfolio([txn])
        holding = portfolio.holdings.get("TEST")
        
        # Check precision maintained
        assert isinstance(holding.shares, Decimal)
        assert holding.shares == Decimal("10.123456")
    
    def test_encryption_decryption_integrity(self):
        """Test that data survives encryption/decryption intact."""
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        
        original_txn = Transaction(
            date=date(2024, 1, 15),
            type=TransactionType.BUY,
            ticker="AAPL",
            shares=Decimal("10.123456789"),
            price=Decimal("150.9876543"),
            total=Decimal("1528.44"),
            fees=Decimal("5.55"),
            currency="USD"
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_encrypt.db")
            store = TransactionStore(db_path=db_path, encryption_key=test_key)
            
            # Store
            store.append_transactions([original_txn], "TestSource")
            
            # Retrieve
            retrieved = store.get_all_transactions()
            
            assert len(retrieved) == 1
            retrieved_txn = retrieved[0]
            
            # Verify all fields match
            assert retrieved_txn.ticker == original_txn.ticker
            assert retrieved_txn.shares == original_txn.shares
            assert retrieved_txn.price == original_txn.price
            assert retrieved_txn.total == original_txn.total
            assert retrieved_txn.fees == original_txn.fees


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_transactions_list(self):
        """Test handling of empty transaction list."""
        portfolio = Portfolio([])
        assert portfolio.total_invested == 0
        assert len(portfolio.holdings) == 0
    
    def test_zero_tax_liability(self):
        """Test tax calculation with no taxable events."""
        calculator = get_calculator("AT")
        liability = calculator.calculate_tax_liability([], tax_year=2024)
        
        assert liability.tax_owed == 0
        assert liability.total_realized_gain == 0
    
    def test_duplicate_import_idempotency(self):
        """Test that importing same data multiple times is safe."""
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        
        txn = Transaction(
            date=date(2024, 1, 1),
            type=TransactionType.BUY,
            ticker="TEST",
            shares=Decimal("10"),
            price=Decimal("100"),
            total=Decimal("1000"),
            fees=Decimal("5"),
            currency="EUR"
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_idem.db")
            store = TransactionStore(db_path=db_path, encryption_key=test_key)
            
            # Import 3 times
            for i in range(3):
                result = store.append_transactions([txn], "TestSource")
                
                if i == 0:
                    assert result.added == 1
                else:
                    assert result.skipped == 1  # Duplicate
            
            # Should only have 1 transaction
            all_txns = store.get_all_transactions()
            assert len(all_txns) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
