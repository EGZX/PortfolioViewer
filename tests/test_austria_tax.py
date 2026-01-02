"""
Unit Tests for Austrian Tax Calculator

Tests Austria-specific tax calculation with KESt rules.

Copyright (c) 2026 Andre. All rights reserved.
"""

import pytest
from datetime import date
from decimal import Decimal

from modules.tax.tax_events import TaxEvent, LotMatchingMethod
from modules.tax.calculators.base import get_calculator
from modules.tax.calculators.austria import AustriaTaxCalculator


class TestAustrianTaxCalculator:
    """Test Austria-specific tax calculations."""
    
    @pytest.fixture
    def calculator(self):
        """Provide an Austria calculator instance."""
        return AustriaTaxCalculator()
    
    @pytest.fixture
    def sample_stock_gain(self):
        """Create a sample stock sale with gain."""
        return TaxEvent(
            event_id="AT-STOCK-001",
            ticker="VOW3",
            isin="DE0007664039",
            asset_name="Volkswagen AG",
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
    def sample_stock_loss(self):
        """Create a sample stock sale with loss."""
        return TaxEvent(
            event_id="AT-STOCK-002",
            ticker="BMW",
            isin="DE0005190003",
            asset_name="BMW AG",
            asset_type="Stock",
            date_sold=date(2024, 8, 1),
            date_acquired=date(2023, 6, 1),
            quantity_sold=Decimal("50"),
            proceeds_base=Decimal("3000.00"),
            cost_basis_base=Decimal("5000.00"),
            realized_gain=Decimal("-2000.00"),
            holding_period_days=427,
            lot_matching_method=LotMatchingMethod.FIFO
        )
    
    @pytest.fixture
    def sample_crypto_gain(self):
        """Create a sample crypto sale with gain."""
        return TaxEvent(
            event_id="AT-CRYPTO-001",
            ticker="BTC",
            asset_name="Bitcoin",
            asset_type="Crypto",
            date_sold=date(2024, 9, 1),
            date_acquired=date(2024, 1, 1),
            quantity_sold=Decimal("0.5"),
            proceeds_base=Decimal("30000.00"),
            cost_basis_base=Decimal("20000.00"),
            realized_gain=Decimal("10000.00"),
            holding_period_days=244,
            lot_matching_method=LotMatchingMethod.FIFO
        )
    
    def test_calculator_registration(self):
        """Test that Austria calculator is properly registered."""
        calc = get_calculator("AT")
        assert isinstance(calc, AustriaTaxCalculator)
        assert calc.get_jurisdiction_code() == "AT"
        assert calc.get_jurisdiction_name() == "Austria"
    
    def test_basic_stock_gain(self, calculator, sample_stock_gain):
        """
        Test basic stock gain calculation.
        
        Scenario:
        - €5,000 stock gain
        - Tax: €5,000 * 27.5% = €1,375
        - No allowance in Austria
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_gain],
            tax_year=2024
        )
        
        assert liability.jurisdiction == "Austria (AT)"
        assert liability.tax_year == 2024
        assert liability.total_realized_gain == Decimal("5000.00")
        assert liability.taxable_gain == Decimal("5000.00")
        
        # Tax calculation: 5000 * 0.275 = 1375
        expected_tax = Decimal("1375.00")
        assert liability.tax_owed == expected_tax
        
        # Check breakdown
        assert liability.breakdown["Stock_gains"] == Decimal("5000.00")
        assert liability.breakdown["Stock_losses"] == Decimal("0")
        assert liability.breakdown["Stock_net"] == Decimal("5000.00")
    
    def test_stock_loss(self, calculator, sample_stock_loss):
        """
        Test stock loss handling.
        
        Scenario:
        - €2,000 stock loss
        - No tax owed (loss)
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_loss],
            tax_year=2024
        )
        
        assert liability.total_realized_gain == Decimal("-2000.00")
        assert liability.taxable_gain == Decimal("-2000.00")
        assert liability.tax_owed == Decimal("0")
        
        # Check breakdown
        assert liability.breakdown["Stock_gains"] == Decimal("0")
        assert liability.breakdown["Stock_losses"] == Decimal("2000.00")
        assert liability.breakdown["Stock_net"] == Decimal("-2000.00")
        
        # Should mention loss carry-forward
        assert "loss" in liability.notes.lower()
        assert "carried forward" in liability.notes.lower()
    
    def test_mixed_stock_gain_and_loss(
        self,
        calculator,
        sample_stock_gain,
        sample_stock_loss
    ):
        """
        Test offsetting gains with losses.
        
        Scenario:
        - €5,000 gain
        - €2,000 loss
        - Net: €3,000
        - Tax: €3,000 * 27.5% = €825
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_gain, sample_stock_loss],
            tax_year=2024
        )
        
        assert liability.breakdown["Stock_gains"] == Decimal("5000.00")
        assert liability.breakdown["Stock_losses"] == Decimal("2000.00")
        assert liability.breakdown["Stock_net"] == Decimal("3000.00")
        
        assert liability.total_realized_gain == Decimal("3000.00")
        assert liability.taxable_gain == Decimal("3000.00")
        
        # Tax: 3000 * 0.275 = 825
        expected_tax = Decimal("825.00")
        assert liability.tax_owed == expected_tax
    
    def test_crypto_taxation(self, calculator, sample_crypto_gain):
        """
        Test cryptocurrency taxation.
        
        Scenario:
        - €10,000 crypto gain
        - Always taxed at 27.5% (no holding period exemption for new crypto)
        - Tax: €10,000 * 27.5% = €2,750
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_crypto_gain],
            tax_year=2024
        )
        
        assert liability.total_realized_gain == Decimal("10000.00")
        assert liability.taxable_gain == Decimal("10000.00")
        
        # Tax: 10000 * 0.275 = 2750
        expected_tax = Decimal("2750.00")
        assert liability.tax_owed == expected_tax
        
        # Check categorization
        assert liability.breakdown["Crypto_gains"] == Decimal("10000.00")
        assert liability.breakdown["Crypto_losses"] == Decimal("0")
    
    def test_separate_reporting_by_asset_type(
        self,
        calculator,
        sample_stock_gain,
        sample_stock_loss,
        sample_crypto_gain
    ):
        """
        Test that gains/losses are reported separately by asset type.
        
        Scenario:
        - Stock: €5,000 gain, €2,000 loss = €3,000 net
        - Crypto: €10,000 gain = €10,000 net
        - Total: €13,000 taxable
        - Tax: €13,000 * 27.5% = €3,575
        """
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_gain, sample_stock_loss, sample_crypto_gain],
            tax_year=2024
        )
        
        # Stock breakdown
        assert liability.breakdown["Stock_gains"] == Decimal("5000.00")
        assert liability.breakdown["Stock_losses"] == Decimal("2000.00")
        assert liability.breakdown["Stock_net"] == Decimal("3000.00")
        
        # Crypto breakdown
        assert liability.breakdown["Crypto_gains"] == Decimal("10000.00")
        assert liability.breakdown["Crypto_losses"] == Decimal("0")
        assert liability.breakdown["Crypto_net"] == Decimal("10000.00")
        
        # Total
        assert liability.breakdown["total_gains"] == Decimal("15000.00")
        assert liability.breakdown["total_losses"] == Decimal("2000.00")
        assert liability.breakdown["net_taxable_gain"] == Decimal("13000.00")
        
        # Tax: 13000 * 0.275 = 3575
        expected_tax = Decimal("3575.00")
        assert liability.tax_owed == expected_tax
    
    def test_no_annual_allowance(self, calculator):
        """
        Test that there is NO annual allowance in Austria.
        
        Scenario:
        - Even small gains (€100) are fully taxed
        """
        small_gain = TaxEvent(
            event_id="AT-SMALL-001",
            ticker="MSFT",
            asset_type="Stock",
            date_sold=date(2024, 5, 1),
            date_acquired=date(2024, 1, 1),
            quantity_sold=Decimal("5"),
            proceeds_base=Decimal("600.00"),
            cost_basis_base=Decimal("500.00"),
            realized_gain=Decimal("100.00"),
            holding_period_days=121,
            lot_matching_method=LotMatchingMethod.FIFO
        )
        
        liability = calculator.calculate_tax_liability(
            events=[small_gain],
            tax_year=2024
        )
        
        # No allowance - full €100 is taxable
        assert liability.taxable_gain == Decimal("100.00")
        assert liability.tax_owed == Decimal("27.50")  # 100 * 0.275
    
    def test_no_holding_period_exemption(self, calculator):
        """
        Test that holding period does NOT matter (abolished in 2011).
        
        Scenario:
        - Stock held 3 years - still taxed
        - Stock held 3 days - also taxed at same rate
        """
        long_hold = TaxEvent(
            event_id="AT-LONG-001",
            ticker="AAPL",
            asset_type="Stock",
            date_sold=date(2024, 6, 1),
            date_acquired=date(2021, 6, 1),
            quantity_sold=Decimal("10"),
            proceeds_base=Decimal("2000.00"),
            cost_basis_base=Decimal("1000.00"),
            realized_gain=Decimal("1000.00"),
            holding_period_days=1096,  # 3 years
            lot_matching_method=LotMatchingMethod.FIFO
        )
        
        short_hold = TaxEvent(
            event_id="AT-SHORT-001",
            ticker="GOOGL",
            asset_type="Stock",
            date_sold=date(2024, 6, 4),
            date_acquired=date(2024, 6, 1),
            quantity_sold=Decimal("10"),
            proceeds_base=Decimal("2000.00"),
            cost_basis_base=Decimal("1000.00"),
            realized_gain=Decimal("1000.00"),
            holding_period_days=3,  # 3 days
            lot_matching_method=LotMatchingMethod.FIFO
        )
        
        # Both should be taxed identically
        liability_long = calculator.calculate_tax_liability([long_hold], 2024)
        liability_short = calculator.calculate_tax_liability([short_hold], 2024)
        
        assert liability_long.tax_owed == liability_short.tax_owed == Decimal("275.00")
    
    def test_no_events_for_year(self, calculator, sample_stock_gain):
        """Test calculation when no events match the tax year."""
        # Event is in 2024, but we ask for 2025
        liability = calculator.calculate_tax_liability(
            events=[sample_stock_gain],
            tax_year=2025
        )
        
        assert liability.total_realized_gain == Decimal("0")
        assert liability.tax_owed == Decimal("0")
        assert "No taxable events" in liability.notes
    
    def test_fees_tracking_note(self, calculator):
        """
        Test that fees rule is documented in assumptions.
        
        CRITICAL: Fees cannot reduce taxable gains in Austria
        """
        liability = calculator.calculate_tax_liability(
            events=[],
            tax_year=2024
        )
        
        # Check that fee rule is documented
        assumptions_text = " ".join(liability.assumptions)
        assert "fees" in assumptions_text.lower()
        assert "do not reduce" in assumptions_text.lower() or "cannot" in assumptions_text.lower()
    
    def test_asset_type_detection(self, calculator):
        """Test automatic asset type detection from ticker."""
        btc_event = TaxEvent(
            event_id="AT-BTC-001",
            ticker="BTC",
            asset_type="",  # Empty, should detect from ticker
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
        
        # Should be categorized as Crypto
        assert "Crypto_gains" in liability.breakdown
        assert liability.breakdown["Crypto_gains"] == Decimal("10000.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
