"""
Unit Tests for Encrypted TransactionStore

Tests database operations, encryption, deduplication, and source management.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import pytest
import tempfile
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from modules.viewer.transaction_store import TransactionStore, EncryptionManager
from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType


class TestEncryptionManager:
    """Test encryption/decryption functionality."""
    
    @pytest.fixture
    def encryption(self):
        """Provide encryption manager with test key."""
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        return EncryptionManager(test_key)
    
    def test_encrypt_decrypt_string(self, encryption):
        """Test basic string encryption and decryption."""
        original = "Test sensitive data"
        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)
        
        assert encrypted != original
        assert decrypted == original
    
    def test_encrypt_decrypt_decimal(self, encryption):
        """Test Decimal encryption and decryption."""
        original = Decimal("123.456789")
        encrypted = encryption.encrypt_decimal(original)
        decrypted = encryption.decrypt_decimal(encrypted)
        
        assert decrypted == original
    
    def test_encrypt_none(self, encryption):
        """Test that None values are handled correctly."""
        assert encryption.encrypt(None) is None
        assert encryption.decrypt(None) is None
        assert encryption.encrypt_decimal(None) is None
        assert encryption.decrypt_decimal(None) is None


class TestTransactionStore:
    """Test TransactionStore database operations."""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing."""
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_transactions.db")
            store = TransactionStore(db_path=db_path, encryption_key=test_key)
            yield store
    
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
    
    def test_init_database(self, temp_db):
        """Test database initialization."""
        # Check that tables exist
        with temp_db._get_conn() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        
        table_names = [t[0] for t in tables]
        assert "transactions" in table_names
        assert "import_history" in table_names
    
    def test_append_transactions(self, temp_db, sample_transactions):
        """Test adding transactions to store."""
        result = temp_db.append_transactions(
            sample_transactions,
            source_name="Test_Broker"
        )
        
        assert result.added == 3
        assert result.skipped == 0
        assert len(result.errors) == 0
        assert result.total_count == 3
    
    def test_deduplication(self, temp_db, sample_transactions):
        """Test that duplicate transactions are skipped."""
        # Add first time
        result1 = temp_db.append_transactions(
            sample_transactions,
            source_name="Broker1"
        )
        
        # Add same transactions again (duplicates)
        result2 = temp_db.append_transactions(
            sample_transactions,
            source_name="Broker2"
        )
        
        assert result1.added == 3
        assert result2.added == 0
        assert result2.skipped == 3  # All should be skipped as duplicates
    
    def test_get_all_transactions(self, temp_db, sample_transactions):
        """Test retrieving all transactions."""
        temp_db.append_transactions(sample_transactions, "TestSource")
        
        retrieved = temp_db.get_all_transactions()
        
        assert len(retrieved) == 3
        assert all(isinstance(t, Transaction) for t in retrieved)
        
        # Check data integrity (encryption/decryption worked)
        assert retrieved[0].ticker == "AAPL"
        assert retrieved[0].shares == Decimal("10")
        assert retrieved[0].price == Decimal("150.00")
    
    def test_date_filtering(self, temp_db, sample_transactions):
        """Test date range filtering."""
        temp_db.append_transactions(sample_transactions, "TestSource")
        
        # Get transactions in February only
        filtered = temp_db.get_all_transactions(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 29)
        )
        
        assert len(filtered) == 1
        assert filtered[0].ticker == "MSFT"
    
    def test_source_filtering(self, temp_db, sample_transactions):
        """Test filtering by source name."""
        # Add to two different sources
        temp_db.append_transactions([sample_transactions[0]], "Broker_A")
        temp_db.append_transactions([sample_transactions[1]], "Broker_B")
        
        # Get only from Broker_A
        filtered = temp_db.get_all_transactions(source_filter=["Broker_A"])
        
        assert len(filtered) == 1
        assert filtered[0].ticker == "AAPL"
    
    def test_get_sources(self, temp_db, sample_transactions):
        """Test getting list of sources."""
        temp_db.append_transactions([sample_transactions[0]], "Broker_A")
        temp_db.append_transactions([sample_transactions[1]], "Broker_B")
        
        sources = temp_db.get_sources()
        
        assert len(sources) == 2
        assert "Broker_A" in sources
        assert "Broker_B" in sources
    
    def test_delete_by_source(self, temp_db, sample_transactions):
        """Test deleting transactions by source."""
        temp_db.append_transactions([sample_transactions[0]], "Broker_A")
        temp_db.append_transactions([sample_transactions[1]], "Broker_B")
        
        # Delete Broker_A
        deleted = temp_db.delete_by_source("Broker_A")
        
        assert deleted == 1
        
        # Verify only Broker_B remains
        remaining = temp_db.get_all_transactions()
        assert len(remaining) == 1
        assert remaining[0].ticker == "MSFT"
    
    def test_transaction_count_by_source(self, temp_db, sample_transactions):
        """Test counting transactions per source."""
        temp_db.append_transactions(sample_transactions[:2], "Broker_A")
        temp_db.append_transactions([sample_transactions[2]], "Broker_B")
        
        counts = temp_db.get_transaction_count_by_source()
        
        assert counts["Broker_A"] == 2
        assert counts["Broker_B"] == 1
    
    def test_import_history(self, temp_db, sample_transactions):
        """Test import history tracking."""
        temp_db.append_transactions(sample_transactions, "TestBroker")
        
        history = temp_db.get_import_history()
        
        assert len(history) >= 1
        assert history[0]['source_name'] == "TestBroker"
        assert history[0]['transactions_added'] == 3
        assert history[0]['status'] == 'success'
    
    def test_encryption_in_database(self, temp_db, sample_transactions):
        """Test that sensitive data is actually encrypted in database."""
        temp_db.append_transactions([sample_transactions[0]], "TestSource")
        
        # Read raw data from database
        with temp_db._get_conn() as conn:
            row = conn.execute("SELECT * FROM transactions LIMIT 1").fetchone()
        
        # Encrypted fields should not contain plain text
        assert row['shares_enc'] is not None
        assert "10" not in row['shares_enc']  # Original value shouldn't be visible
        
        # But ticker/ISIN should be plain (needed for queries)
        assert row['ticker'] == "AAPL"
        assert row['isin'] == "US0378331005"
    
    def test_hash_generation_consistency(self, temp_db):
        """Test that identical transactions generate same hash."""
        txn1 = Transaction(
            date=date(2024, 1, 1),
            type=TransactionType.BUY,
            ticker="TEST",
            shares=Decimal("10"),
            price=Decimal("100"),
            total=Decimal("1000"),
            fees=Decimal("5"),
            currency="EUR"
        )
        
        txn2 = Transaction(
            date=date(2024, 1, 1),
            type=TransactionType.BUY,
            ticker="TEST",
            shares=Decimal("10.000000"),  # Same value, different precision
            price=Decimal("100.0000"),
            total=Decimal("1000.00"),
            fees=Decimal("5.00"),
            currency="EUR"
        )
        
        hash1 = temp_db._generate_transaction_hash(txn1)
        hash2 = temp_db._generate_transaction_hash(txn2)
        
        assert hash1 == hash2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
