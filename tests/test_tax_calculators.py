"""
Unit Tests for Tax Calculator System

Tests the base tax calculator architecture and Germany-specific implementation.

Copyright (c) 2026 Andre. All rights reserved.
"""

import pytest
from datetime import date
from decimal import Decimal

from calculators.tax_events import TaxEvent, LotMatchingMethod
from calculators.tax_calculators.base import (
    TaxCalculator,
    get_calculator,
    list_available_jurisdictions
)
from calculators.tax_calculators.germany import GermanyTaxCalculator


class TestTaxCalculatorFactory:
    """Test the calculator factory and registration system."""
    
    def test_get_germany_calculator(self):
        """Test retrieving Germany calculator."""
        calc = get_calculator("DE")
        assert isinstance(calc, GermanyTaxCalculator)
        assert calc.get_jurisdiction_code() == "DE"
        assert calc.get_jurisdiction_name() == "Germany"
    
    def test_case_insensitive_lookup(self):
        """Test that jurisdiction codes are case-insensitive."""
        calc_upper = get_calculator("DE")
        calc_lower = get_calculator("de")
        
        assert type(calc_upper) == type(calc_lower)
    
    def test_invalid_jurisdiction_raises_error(self):
        """Test that invalid jurisdiction raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            get_calculator("XX")
    
    def test_list_available_jurisdictions(self):
        """Test listing available calculators."""
        jurisdictions = list_available_jurisdictions()
        assert "DE" in jurisdictions
        assert len(jurisdictions) >= 1


class TestGermanyTaxCalculator:
    """Test Germany-specific tax calculations."""
    
    @pytest.fixture
    def calculator(self):
        """Provide a Germany calculator instance."""
        return GermanyTaxCalculator()
    
    @pytest.fixture
    def sample_stock_event(self):
        """Create a sample stock sale event."""
        return TaxEvent(
            event_id="TEST-001",
            ticker="AAPL",
            isin="US0378331005",
            asset_name="Apple Inc.",
            asset_type="Stock",
            date_sold=date(2024, 6, 15),
            date_acquired=date(2023, 1, 10),
            quantity_sold=Decimal("100"),
            proceeds_base=Decimal("15000.00"),
            cost_basis_base=Decimal("10000.00"),
            realized_gain=Decimal("5000.00"),
            holding_period_days=522,
            lot_matching_method=LotMatchingMethod.FIFO
        )
    
    @pytest.fixture
    def sample_crypto_short_term_event(self):
        """Create a sample crypto event held < 1 year."""
        return TaxEvent(
            event_id="TEST-002",
            ticker="BTC",
            asset_name="Bitcoin",
            asset_type="Crypto",
            date_sold=date(2024, 8, 1),
            date_acquired=date(2024, 3, 1),
            quantity_sold=Decimal("0.5"),
            proceeds_base=Decimal("30000.00"),
            cost_basis_base=Decimal("25000.00"),
            realized_gain=Decimal("5000.00"),
            holding_period_days=153,
            lot_matching_method=LotMatchingMethod.FIFO
        )
    
    @pytest.fixture
    def sample_crypto_long_term_event(self):
        """Create a sample crypto event held > 1 year."""
        return TaxEvent(
            event_id="TEST-003",
            ticker="ETH",
            asset_name="Ethereum",
            asset_type="Crypto",
            date_sold=date(2024, 9, 1),
            date_acquired=date(2023, 1, 1),
            quantity_sold=Decimal("10"),
            proceeds_base=Decimal("25000.00"),
            cost_basis_base=Decimal("15000.00"),
            realized_gain=Decimal("10000.00"),
            holding_period_days=609,
            lot_matching_method=LotMatchingMethod.FIFO
        )
    
    def test_basic_stock_calculation(self, calculator, sample_stock_event):
        """
        Test basic stock gain calculation.
        
        Scenario:
        - €5,000 gain on stock
        - €1,000 allowance = €4,000 taxable
        - Tax: €4,000 * 25% = €1,000
        - Soli: €1,000 * 5.5% = €55
        - Total tax: €1,055
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_event],
            tax_year=2024
        )
        
        assert liability.jurisdiction == "Germany (DE)"
        assert liability.tax_year == 2024
        assert liability.total_realized_gain == Decimal("5000.00")
        assert liability.taxable_gain == Decimal("4000.00")  # After allowance
        
        # Tax calculation
        expected_base_tax = Decimal("1000.00")  # 4000 * 0.25
        expected_soli = Decimal("55.00")  # 1000 * 0.055
        expected_total = Decimal("1055.00")
        
        assert liability.breakdown["capital_gains_tax_25pct"] == expected_base_tax
        assert liability.breakdown["solidarity_surcharge_5_5pct"] == expected_soli
        assert liability.tax_owed == expected_total
    
    def test_crypto_short_term_taxable(self, calculator, sample_crypto_short_term_event):
        """
        Test that crypto held < 1 year is taxable.
        
        Scenario:
        - €5,000 crypto gain (held 153 days)
        - €1,000 allowance = €4,000 taxable
        - Tax: €4,000 * 25% = €1,000
        - Soli: €1,000 * 5.5% = €55
        - Total: €1,055
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_crypto_short_term_event],
            tax_year=2024
        )
        
        assert liability.total_realized_gain == Decimal("5000.00")
        assert liability.taxable_gain == Decimal("4000.00")
        assert liability.tax_owed == Decimal("1055.00")
        
        # Check breakdown
        assert liability.breakdown["crypto_short_term_gain"] == Decimal("5000.00")
        assert liability.breakdown["crypto_long_term_gain"] == Decimal("0")
    
    def test_crypto_long_term_tax_free(self, calculator, sample_crypto_long_term_event):
        """
        Test that crypto held > 1 year is tax-free.
        
        Scenario:
        - €10,000 crypto gain (held 609 days)
        - Should be completely tax-free
        - No tax owed
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_crypto_long_term_event],
            tax_year=2024
        )
        
        # Total realized gain includes the crypto gain
        assert liability.total_realized_gain == Decimal("10000.00")
        
        # But taxable gain is zero (crypto long-term excluded)
        assert liability.taxable_gain == Decimal("0")
        assert liability.tax_owed == Decimal("0")
        
        # Check breakdown
        assert liability.breakdown["crypto_long_term_gain"] == Decimal("10000.00")
        assert "excluded" in liability.notes
    
    def test_mixed_assets(
        self,
        calculator,
        sample_stock_event,
        sample_crypto_short_term_event,
        sample_crypto_long_term_event
    ):
        """
        Test calculation with mixed asset types.
        
        Scenario:
        - Stock: €5,000 gain (taxable)
        - Crypto short: €5,000 gain (taxable)
        - Crypto long: €10,000 gain (tax-free)
        - Total taxable: €10,000
        - After allowance: €9,000
        - Tax: €9,000 * 25% = €2,250
        - Soli: €2,250 * 5.5% = €123.75
        - Total: €2,373.75
        """
        liability = calculator.calculate_tax_liability(
            events=[
                sample_stock_event,
                sample_crypto_short_term_event,
                sample_crypto_long_term_event
            ],
            tax_year=2024
        )
        
        assert liability.total_realized_gain == Decimal("20000.00")
        assert liability.breakdown["taxable_gain_before_allowance"] == Decimal("10000.00")
        assert liability.taxable_gain == Decimal("9000.00")
        assert liability.tax_owed == Decimal("2373.75")
    
    def test_annual_allowance_application(self, calculator):
        """
        Test that annual allowance is correctly applied.
        
        Scenario:
        - €800 gain (below allowance)
        - Should result in zero tax
        """
        small_event = TaxEvent(
            event_id="TEST-004",
            ticker="MSFT",
            asset_type="Stock",
            date_sold=date(2024, 5, 1),
            date_acquired=date(2023, 5, 1),
            quantity_sold=Decimal("10"),
            proceeds_base=Decimal("4800.00"),
            cost_basis_base=Decimal("4000.00"),
            realized_gain=Decimal("800.00"),
            holding_period_days=366,
            lot_matching_method=LotMatchingMethod.FIFO
        )
        
        liability = calculator.calculate_tax_liability(
            events=[small_event],
            tax_year=2024
        )
        
        assert liability.total_realized_gain == Decimal("800.00")
        assert liability.taxable_gain == Decimal("0")  # Fully covered by allowance
        assert liability.tax_owed == Decimal("0")
        assert liability.breakdown["annual_allowance_used"] == Decimal("800.00")
    
    def test_loss_scenario(self, calculator):
        """
        Test handling of capital losses.
        
        Scenario:
        - €2,000 loss
        - Should result in zero tax
        - Loss cannot be carried forward
        """
        loss_event = TaxEvent(
            event_id="TEST-005",
            ticker="GME",
            asset_type="Stock",
            date_sold=date(2024, 11, 1),
            date_acquired=date(2024, 1, 1),
            quantity_sold=Decimal("50"),
            proceeds_base=Decimal("3000.00"),
            cost_basis_base=Decimal("5000.00"),
            realized_gain=Decimal("-2000.00"),
            holding_period_days=305,
            lot_matching_method=LotMatchingMethod.FIFO
        )
        
        liability = calculator.calculate_tax_liability(
            events=[loss_event],
            tax_year=2024
        )
        
        assert liability.total_realized_gain == Decimal("-2000.00")
        assert liability.taxable_gain == Decimal("0")
        assert liability.tax_owed == Decimal("0")
        assert "loss" in liability.notes.lower()
    
    def test_no_events_for_year(self, calculator, sample_stock_event):
        """Test calculation when no events match the tax year."""
        # Event is in 2024, but we ask for 2025
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_event],
            tax_year=2025
        )
        
        assert liability.total_realized_gain == Decimal("0")
        assert liability.tax_owed == Decimal("0")
        assert "No taxable events" in liability.notes
    
    def test_custom_allowance(self, calculator, sample_stock_event):
        """Test using a custom allowance amount."""
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_event],
            tax_year=2024,
            allowance_override=Decimal("2000.00")
        )
        
        # €5,000 gain - €2,000 allowance = €3,000 taxable
        assert liability.taxable_gain == Decimal("3000.00")
        assert liability.breakdown["annual_allowance_used"] == Decimal("2000.00")
    
    def test_without_solidarity_surcharge(self, calculator, sample_stock_event):
        """Test calculation without solidarity surcharge."""
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_event],
            tax_year=2024,
            include_solidarity=False
        )
        
        # Should only have base tax, no soli
        expected_tax = Decimal("1000.00")  # (5000 - 1000) * 0.25
        assert liability.tax_owed == expected_tax
        assert liability.breakdown["solidarity_surcharge_5_5pct"] == Decimal("0")
    
    def test_crypto_detection_by_ticker(self, calculator):
        """Test that crypto is detected by ticker even without asset_type."""
        btc_event = TaxEvent(
            event_id="TEST-006",
            ticker="BTC",
            asset_type="",  # Empty asset type
            date_sold=date(2024, 7, 1),
            date_acquired=date(2024, 5, 1),
            quantity_sold=Decimal("1"),
            proceeds_base=Decimal("50000.00"),
            cost_basis_base=Decimal("40000.00"),
            realized_gain=Decimal("10000.00"),
            holding_period_days=61,
            lot_matching_method=LotMatchingMethod.FIFO
        )
        
        liability = calculator.calculate_tax_liability(
            events=[btc_event],
            tax_year=2024
        )
        
        # Should be treated as crypto short-term
        assert liability.breakdown["crypto_short_term_gain"] == Decimal("10000.00")


class TestTaxCalculatorHelpers:
    """Test helper methods in base TaxCalculator."""
    
    def test_filter_events_by_year(self):
        """Test filtering events by tax year."""
        calc = GermanyTaxCalculator()
        
        events = [
            TaxEvent(
                event_id="2023-001",
                ticker="AAPL",
                date_sold=date(2023, 12, 31),
                date_acquired=date(2023, 1, 1),
                quantity_sold=Decimal("10"),
                proceeds_base=Decimal("1000"),
                cost_basis_base=Decimal("900"),
                realized_gain=Decimal("100"),
                holding_period_days=364,
                lot_matching_method=LotMatchingMethod.FIFO
            ),
            TaxEvent(
                event_id="2024-001",
                ticker="MSFT",
                date_sold=date(2024, 1, 1),
                date_acquired=date(2023, 1, 1),
                quantity_sold=Decimal("10"),
                proceeds_base=Decimal("1000"),
                cost_basis_base=Decimal("900"),
                realized_gain=Decimal("100"),
                holding_period_days=366,
                lot_matching_method=LotMatchingMethod.FIFO
            ),
        ]
        
        filtered_2023 = calc.filter_events_by_year(events, 2023)
        filtered_2024 = calc.filter_events_by_year(events, 2024)
        
        assert len(filtered_2023) == 1
        assert filtered_2023[0].event_id == "2023-001"
        
        assert len(filtered_2024) == 1
        assert filtered_2024[0].event_id == "2024-001"
    
    def test_calculate_total_gain(self):
        """Test summing realized gains."""
        calc = GermanyTaxCalculator()
        
        events = [
            TaxEvent(
                event_id=f"TEST-{i}",
                ticker="TEST",
                date_sold=date(2024, 1, 1),
                date_acquired=date(2023, 1, 1),
                quantity_sold=Decimal("10"),
                proceeds_base=Decimal("1000"),
                cost_basis_base=Decimal("900"),
                realized_gain=Decimal(str(gain)),
                holding_period_days=365,
                lot_matching_method=LotMatchingMethod.FIFO
            )
            for i, gain in enumerate([100, 200, -50, 300])
        ]
        
        total = calc.calculate_total_gain(events)
        assert total == Decimal("550")  # 100 + 200 - 50 + 300


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
