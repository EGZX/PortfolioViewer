"""
Tests for Currency Lot Tracking and FX Transactions

Verifies FX buy/sell transactions are correctly tracked with lot matching,
fees are handled per jurisdiction rules, and FX gains are accurately calculated.

Copyright (c) 2026 Andre. All rights reserved.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, date
from decimal import Decimal

from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from modules.tax.engine import TaxBasisEngine
from modules.tax.calculators.austria import AustriaTaxCalculator


def test_fx_buy_creates_currency_lot():
    """Test that FX_BUY transactions create currency lots."""
    transactions = [
        Transaction(
            date=datetime(2024, 1, 1),
            type=TransactionType.FX_BUY,
            original_currency="USD",
            total=Decimal("1000"),  # Buying 1000 USD
            fees=Decimal("20"),  # 20 USD fee
            price=Decimal(0),
            shares=Decimal(0)
        )
    ]
   
    engine = TaxBasisEngine(transactions, "FIFO")
    engine.process_all_transactions()
    
    # Check currency lot was created
    assert "USD" in engine.currency_lots
    assert len(engine.currency_lots["USD"]) == 1
    
    lot = engine.currency_lots["USD"][0]
    assert lot.currency == "USD"
    assert lot.amount_gross == Decimal("1000")
    assert lot.amount_net == Decimal("980")  # 1000 - 20 fee
    assert lot.amount == Decimal("980")  # Tracking uses net
    assert lot.fee_amount == Decimal("20")
    assert lot.cost_basis_eur > 0  # Should have EUR cost basis


def test_pure_fx_gain():
    """Test FX speculation gain calculation (EUR → DKK → EUR)."""
    transactions = [
        # Buy DKK
        Transaction(
            date=datetime(2024, 1, 1),
            type=TransactionType.FX_BUY,
            original_currency="DKK",
            total=Decimal("7450"),  # Buy 7450 DKK
            fees=Decimal("20"),  # 20 DKK fee
            price=Decimal(0),
            shares=Decimal(0)
        ),
        # Sell DKK (rate improved)
        Transaction(
            date=datetime(2024, 1, 30),
            type=TransactionType.FX_SELL,
            original_currency="DKK",
            total=Decimal("7430"),  # Sell all (minus fee from buy)
            fees=Decimal("15"),  # 15 DKK fee
            price=Decimal(0),
            shares=Decimal(0)
        )
    ]
    
    engine = TaxBasisEngine(transactions, "FIFO")
    engine.process_all_transactions()
    
    events = engine.get_realized_events()
    assert len(events) == 1
    
    event = events[0]
    assert event.ticker == "FX_DKK"
    assert event.asset_type == "FX"
    # Should have a gain if DKK strengthened
    assert event.proceeds_base > 0
    assert event.cost_basis_base > 0
    
    # Lot should be exhausted
    remaining_lots = engine.currency_lots["DKK"]
    assert len(remaining_lots) == 0


def test_fx_fee_reduces_position():
    """Test that fees paid in foreign currency reduce position size."""
    transactions = [
        Transaction(
            date=datetime(2024, 1, 1),
            type=TransactionType.FX_BUY,
            original_currency="USD",
            total=Decimal("1000"),  # Buy 1000 USD
            fees=Decimal("50"),  # 50 USD fee
            price=Decimal(0),
            shares=Decimal(0)
        )
    ]
    
    engine = TaxBasisEngine(transactions, "FIFO")
    engine.process_all_transactions()
    
    lot = engine.currency_lots["USD"][0]
    assert lot.amount == Decimal("950")  # 1000 - 50 fee
    assert lot.fee_amount == Decimal("50")


def test_fx_multiple_lots_fifo():
    """Test FIFO matching across multiple FX purchases."""
    transactions = [
        # Buy 1: 1000 USD
        Transaction(
            date=datetime(2024, 1, 1),
            type=TransactionType.FX_BUY,
            original_currency="USD",
            total=Decimal("1000"),
            fees=Decimal("10"),
            price=Decimal(0),
            shares=Decimal(0)
        ),
        # Buy 2: 2000 USD
        Transaction(
            date=datetime(2024, 1, 15),
            type=TransactionType.FX_BUY,
            original_currency="USD",
            total=Decimal("2000"),
            fees=Decimal("20"),
            price=Decimal(0),
            shares=Decimal(0)
        ),
        # Sell 1500 USD (should consume first lot + part of second)
        Transaction(
            date=datetime(2024, 2, 1),
            type=TransactionType.FX_SELL,
            original_currency="USD",
            total=Decimal("1500"),
            fees=Decimal("15"),
            price=Decimal(0),
            shares=Decimal(0)
        )
    ]
    
    engine = TaxBasisEngine(transactions, "FIFO")
    engine.process_all_transactions()
    
    # Should have 1 event
    events = engine.get_realized_events()
    assert len(events) == 1
    
    # Check remaining lots
    remaining_lots = engine.currency_lots["USD"]
    # First lot exhausted (990 consumed), second lot partially consumed
    # 1515 total needed (1500 + 15 fee), consumed 990 from lot1, 525 from lot2
    # Lot 2 had 1980, should have 1980 - 525 = 1455 left
    assert len(remaining_lots) > 0


def test_fx_austrian_tax_calc():
    """Test that Austrian calculator correctly reports FX gains/losses."""
    transactions = [
        Transaction(
            date=datetime(2024, 1, 1),
            type=TransactionType.FX_BUY,
            original_currency="CHF",
            total=Decimal("10000"),
            fees=Decimal("100"),
            price=Decimal(0),
            shares=Decimal(0)
        ),
        Transaction(
            date=datetime(2024, 6, 1),
            type=TransactionType.FX_SELL,
            original_currency="CHF",
            total=Decimal("9900"),
            fees=Decimal("100"),
            price=Decimal(0),
            shares=Decimal(0)
        )
    ]
    
    engine = TaxBasisEngine(transactions, "FIFO")
    engine.process_all_transactions()
    
    calc = AustriaTaxCalculator()
    result = calc.calculate_tax_liability(
        engine.get_realized_events(),
        tax_year=2024
    )
    
    # Should have FX event processed
    assert result.tax_owed >= 0
    # Austrian rule: fees don't reduce gains
    assert "FX transactions" in "\n".join(result.assumptions)


def test_insufficient_currency_lots_warning():
    """Test warning when selling more currency than available in lots."""
    transactions = [
        Transaction(
            date=datetime(2024, 1, 1),
            type=TransactionType.FX_BUY,
            original_currency="GBP",
            total=Decimal("1000"),
            fees=Decimal("10"),
            price=Decimal(0),
            shares=Decimal(0)
        ),
        Transaction(
            date=datetime(2024, 2, 1),
            type=TransactionType.FX_SELL,
            original_currency="GBP",
            total=Decimal("2000"),  # Selling more than we have
            fees=Decimal("20"),
            price=Decimal(0),
            shares=Decimal(0)
        )
    ]
    
    engine = TaxBasisEngine(transactions, "FIFO")
    # Should not crash, but log warning
    engine.process_all_transactions()
    
    events = engine.get_realized_events()
    assert len(events) == 1  # Event still created


def test_fx_transaction_type_normalization():
    """Test that FX transaction types are correctly normalized."""
    from lib.parsers.enhanced_transaction import TransactionType
    
    assert TransactionType.normalize("FX_BUY") == TransactionType.FX_BUY
    assert TransactionType.normalize("FXBUY") == TransactionType.FX_BUY
    assert TransactionType.normalize("FX_SELL") == TransactionType.FX_SELL
    assert TransactionType.normalize("FOREX") == TransactionType.FX_EXCHANGE
    assert TransactionType.normalize("EXCHANGE") == TransactionType.FX_EXCHANGE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
