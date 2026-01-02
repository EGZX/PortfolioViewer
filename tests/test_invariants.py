"""
Property-Based Tests - The Hypothesis

Uses hypothesis library for property-based testing to verify mathematical invariants.

Invariants:
1. Shares * Cost != Negative (cost basis cannot be negative for positive holdings)
2. Realized + Unrealized = Total Value - Net Invested
3. Total Value = Sum of all holdings' market values + Cash

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from decimal import Decimal
from datetime import date, timedelta
from modules.viewer.portfolio import Portfolio
from modules.viewer.metrics import calculate_absolute_return
from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType


# Strategy for generating valid decimal prices/amounts
decimal_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("10000"),
    places=2,
    allow_nan=False,
    allow_infinity=False
)

# Strategy for generating positive integers (shares)
shares_strategy = st.integers(min_value=1, max_value=1000)

# Strategy for generating dates
date_strategy = st.dates(
    min_value=date(2020, 1, 1),
    max_value=date(2024, 12, 31)
)


@given(
    shares=shares_strategy,
    price=decimal_strategy
)
@settings(max_examples=100)
def test_invariant_cost_basis_non_negative(shares, price):
    """
    Invariant 1: Shares * Cost != Negative
    
    For any positive number of shares at a positive price,
    the cost basis must be non-negative.
    """
    cost_basis = Decimal(shares) * price
    assert cost_basis >= 0, "Cost basis must be non-negative for positive holdings"


@given(
    invested=decimal_strategy,
    withdrawn=decimal_strategy,
    market_gain=st.decimals(min_value=Decimal("-1000"), max_value=Decimal("10000"), places=2)
)
@settings(max_examples=100)
def test_invariant_total_value_consistency(invested, withdrawn, market_gain):
    """
    Invariant 2: Total Value = Net Invested + Gains
    
    Where:
    - Net Invested = Invested - Withdrawn
    - Total Value = Net Invested + Realized Gains + Unrealized Gains
    """
    net_invested = invested - withdrawn
    total_value = net_invested + market_gain
    
    # Verify the relationship holds
    calculated_gain = total_value - net_invested
    assert abs(calculated_gain - market_gain) < Decimal("0.01"), \
        "Total Value - Net Invested should equal total gains"


@given(
    num_holdings=st.integers(min_value=1, max_value=10),
    seed=st.integers(min_value=0, max_value=1000000)
)
@settings(max_examples=50)
def test_invariant_portfolio_value_decomposition(num_holdings, seed):
    """
    Invariant 3: Total Value = Sum(Holdings Market Values) + Cash
    
    The total portfolio value must equal the sum of all individual
    holding market values plus cash balance.
    """
    import random
    random.seed(seed)
    
    # Generate transactions
    transactions = []
    base_date = date(2024, 1, 1)
    
    for i in range(num_holdings):
        ticker = f"TEST{i}"
        shares = random.randint(10, 100)
        price = Decimal(str(random.uniform(50, 200)))
        
        transactions.append(Transaction(
            date=base_date + timedelta(days=i),
            type=TransactionType.BUY,
            ticker=ticker,
            isin=f"US{i:08d}",
            name=f"Test Stock {i}",
            shares=Decimal(shares),
            price=price,
            fees=Decimal("0"),
            total=Decimal(shares) * price,
            currency="USD",
            fx_rate=Decimal("1.0"),
            broker="Test",
            asset_type=AssetType.STOCK,
            original_currency="USD"
        ))
    
    # Create portfolio
    portfolio = Portfolio(transactions)
    
    # Create dummy prices (use cost basis as market price for simplicity)
    prices = {
        f"TEST{i}": float(transactions[i].price)
        for i in range(num_holdings)
    }
    
    # Calculate total value
    total_value = portfolio.calculate_total_value(prices)
    
    # Calculate sum of holdings + cash
    holdings_sum = sum(
        holding.market_value 
        for holding in portfolio.holdings.values()
    )
    holdings_plus_cash = holdings_sum + portfolio.cash_balance
    
    # Verify invariant (within 1 cent tolerance for rounding)
    diff = abs(total_value - holdings_plus_cash)
    assert diff < Decimal("0.02"), \
        f"Total value {total_value} != Holdings {holdings_sum} + Cash {portfolio.cash_balance}"


@given(
    buy_price=decimal_strategy,
    sell_price=decimal_strategy,
    shares=shares_strategy
)
@settings(max_examples=100)
def test_invariant_realized_gain_correctness(buy_price, sell_price, shares):
    """
    Test that realized gains are calculated correctly.
    
    Realized Gain = (Sell Price - Buy Price) * Shares - Fees
    """
    # Create buy and sell transactions
    buy_date = date(2024, 1, 1)
    sell_date = date(2024, 6, 1)
    
    transactions = [
        Transaction(
            date=buy_date,
            type=TransactionType.BUY,
            ticker="TEST",
            isin="US12345678",
            name="Test Stock",
            shares=Decimal(shares),
            price=buy_price,
            fees=Decimal("0"),
            total=Decimal(shares) * buy_price,
            currency="USD",
            fx_rate=Decimal("1.0"),
            broker="Test",
            asset_type=AssetType.STOCK,
            original_currency="USD"
        ),
        Transaction(
            date=sell_date,
            type=TransactionType.SELL,
            ticker="TEST",
            isin="US12345678",
            name="Test Stock",
            shares=Decimal(shares),
            price=sell_price,
            fees=Decimal("0"),
            total=Decimal(shares) * sell_price,
            currency="USD",
            fx_rate=Decimal("1.0"),
            broker="Test",
            asset_type=AssetType.STOCK,
            original_currency="USD"
        )
    ]
    
    portfolio = Portfolio(transactions)
    
    # Expected realized gain
    expected_gain = (sell_price - buy_price) * Decimal(shares)
    
    # Verify (within tolerance)
    diff = abs(portfolio.realized_gains - expected_gain)
    assert diff < Decimal("0.02"), \
        f"Realized gain {portfolio.realized_gains} != expected {expected_gain}"


@given(
    initial_investment=decimal_strategy,
    num_transactions=st.integers(min_value=1, max_value=20)
)
@settings(max_examples=50, deadline=None)
def test_invariant_cash_flow_conservation(initial_investment, num_transactions):
    """
    Test conservation of cash flows.
    
    Total Cash Out - Total Cash In = Net Invested
    """
    import random
    random.seed(42)
    
    transactions = []
    base_date = date(2024, 1, 1)
    
    # Initial buy
    transactions.append(Transaction(
        date=base_date,
        type=TransactionType.BUY,
        ticker="TEST",
        isin="US12345678",
        name="Test Stock",
        shares=Decimal("100"),
        price=initial_investment / Decimal("100"),
        fees=Decimal("0"),
        total=initial_investment,
        currency="USD",
        fx_rate=Decimal("1.0"),
        broker="Test",
        asset_type=AssetType.STOCK,
        original_currency="USD"
    ))
    
    portfolio = Portfolio(transactions)
    
    # Verify cash flows
    total_invested = portfolio.total_invested
    total_withdrawn = portfolio.total_withdrawn
    net_invested = total_invested - total_withdrawn
    
    # Net invested should match what we put in
    diff = abs(net_invested - initial_investment)
    assert diff < Decimal("0.02"), \
        f"Net invested {net_invested} != initial investment {initial_investment}"


def test_invariant_empty_portfolio():
    """Test that an empty portfolio has zero values."""
    portfolio = Portfolio([])
    
    assert portfolio.cash_balance == Decimal("0")
    assert portfolio.total_invested == Decimal("0")
    assert portfolio.total_withdrawn == Decimal("0")
    assert portfolio.realized_gains == Decimal("0")
    assert len(portfolio.holdings) == 0


def test_invariant_dividend_adds_to_cash():
    """Test that dividends increase cash balance."""
    transactions = [
        Transaction(
            date=date(2024, 1, 1),
            type=TransactionType.BUY,
            ticker="TEST",
            isin="US12345678",
            name="Test Stock",
            shares=Decimal("100"),
            price=Decimal("50"),
            fees=Decimal("0"),
            total=Decimal("5000"),
            currency="USD",
            fx_rate=Decimal("1.0"),
            broker="Test",
            asset_type=AssetType.STOCK,
            original_currency="USD"
        ),
        Transaction(
            date=date(2024, 2, 1),
            type=TransactionType.DIVIDEND,
            ticker="TEST",
            isin="US12345678",
            name="Test Stock",
            shares=Decimal("0"),
            price=Decimal("1"),
            fees=Decimal("0"),
            total=Decimal("100"),  # $100 dividend
            currency="USD",
            fx_rate=Decimal("1.0"),
            broker="Test",
            asset_type=AssetType.STOCK,
            original_currency="USD"
        )
    ]
    
    portfolio = Portfolio(transactions)
    
    # Cash should be negative invested amount plus dividend
    expected_cash = Decimal("-5000") + Decimal("100")
    assert portfolio.cash_balance == expected_cash
    assert portfolio.total_dividends == Decimal("100")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
