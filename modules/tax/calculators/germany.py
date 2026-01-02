"""
German Tax Calculator (Abgeltungssteuer)

Implements Germany's capital gains tax rules:
- 25% flat tax on capital gains (Abgeltungssteuer)
- 5.5% solidarity surcharge on the tax amount (Solidaritätszuschlag)
- €1,000 annual tax-free allowance (Sparer-Pauschbetrag)
- Cryptocurrency: tax-free if held > 1 year, otherwise taxable as private sale

References:
- §20 EStG (Income Tax Act)
- §32d EStG (Flat tax rate)

Copyright (c) 2026 Andre. All rights reserved.
"""

from typing import List
from decimal import Decimal
from datetime import date

from modules.tax.tax_events import TaxEvent, TaxLiability
from modules.tax.calculators.base import TaxCalculator, register_calculator


@register_calculator("DE")
class GermanyTaxCalculator(TaxCalculator):
    """
    Tax calculator for Germany (Abgeltungssteuer system).
    
    Key Rules:
    - Stocks/ETFs: Always taxable at 25% + 5.5% solidarity surcharge
    - Crypto: Tax-free if held > 1 year, else taxable as private sale
    - Annual allowance: €1,000 (Sparer-Pauschbetrag)
    - Losses can offset gains within the same year
    """
    
    # Tax rates (as of 2024)
    CAPITAL_GAINS_TAX_RATE = Decimal("0.25")  # 25%
    SOLIDARITY_SURCHARGE_RATE = Decimal("0.055")  # 5.5% of tax
    ANNUAL_ALLOWANCE = Decimal("1000.00")  # €1,000
    
    # Crypto holding period threshold
    CRYPTO_HOLDING_PERIOD_DAYS = 365  # 1 year
    
    def get_jurisdiction_name(self) -> str:
        """Return human-readable jurisdiction name."""
        return "Germany"
    
    def get_jurisdiction_code(self) -> str:
        """Return ISO jurisdiction code."""
        return "DE"
    
    def calculate_tax_liability(
        self,
        events: List[TaxEvent],
        tax_year: int,
        **kwargs
    ) -> TaxLiability:
        """
        Calculate German capital gains tax liability.
        
        Args:
            events: All tax events (will be filtered by year)
            tax_year: Calendar year for tax calculation
            **kwargs: Optional parameters:
                - allowance_override: Custom allowance amount (default: €1,000)
                - include_solidarity: Whether to include Soli (default: True)
        
        Returns:
            TaxLiability with German tax calculation
        """
        # Extract optional parameters
        allowance = Decimal(kwargs.get("allowance_override", self.ANNUAL_ALLOWANCE))
        include_solidarity = kwargs.get("include_solidarity", True)
        
        # Filter events to tax year
        year_events = self.filter_events_by_year(events, tax_year)
        
        if not year_events:
            return self._create_zero_liability(tax_year, allowance, include_solidarity)
        
        # Separate events by asset type
        regular_events = []  # Stocks, ETFs, bonds
        crypto_short_term = []  # Crypto held <= 1 year
        crypto_long_term = []  # Crypto held > 1 year (tax-free)
        
        for event in year_events:
            if self._is_crypto(event):
                if event.holding_period_days > self.CRYPTO_HOLDING_PERIOD_DAYS:
                    crypto_long_term.append(event)
                else:
                    crypto_short_term.append(event)
            else:
                regular_events.append(event)
        
        # Calculate gains by category
        regular_gain = self.calculate_total_gain(regular_events)
        crypto_short_gain = self.calculate_total_gain(crypto_short_term)
        crypto_long_gain = self.calculate_total_gain(crypto_long_term)
        
        # Total taxable gain (crypto long-term is excluded)
        total_taxable_gain = regular_gain + crypto_short_gain
        
        # Apply annual allowance
        taxable_gain_after_allowance = max(
            Decimal(0),
            total_taxable_gain - allowance
        )
        
        # Calculate base tax (25%)
        base_tax = taxable_gain_after_allowance * self.CAPITAL_GAINS_TAX_RATE
        
        # Calculate solidarity surcharge (5.5% of base tax)
        solidarity_tax = Decimal(0)
        if include_solidarity:
            solidarity_tax = base_tax * self.SOLIDARITY_SURCHARGE_RATE
        
        # Total tax owed
        total_tax = base_tax + solidarity_tax
        
        # Build detailed breakdown
        breakdown = {
            "regular_realized_gain": regular_gain,
            "crypto_short_term_gain": crypto_short_gain,
            "crypto_long_term_gain": crypto_long_gain,
            "total_realized_gain": regular_gain + crypto_short_gain + crypto_long_gain,
            "taxable_gain_before_allowance": total_taxable_gain,
            "annual_allowance_used": min(allowance, total_taxable_gain),
            "taxable_gain_after_allowance": taxable_gain_after_allowance,
            "capital_gains_tax_25pct": base_tax,
            "solidarity_surcharge_5_5pct": solidarity_tax,
            "total_tax_owed": total_tax,
        }
        
        # Build assumptions list
        assumptions = [
            f"Capital gains tax rate: {self.CAPITAL_GAINS_TAX_RATE * 100}%",
            f"Annual tax-free allowance: €{allowance:,.2f}",
            f"Crypto tax-free holding period: {self.CRYPTO_HOLDING_PERIOD_DAYS} days",
        ]
        
        if include_solidarity:
            assumptions.append(
                f"Solidarity surcharge: {self.SOLIDARITY_SURCHARGE_RATE * 100}% of tax"
            )
        
        # Build notes
        notes = []
        if crypto_long_term:
            notes.append(
                f"{len(crypto_long_term)} crypto event(s) excluded (held > 1 year)"
            )
        if total_taxable_gain < 0:
            notes.append(
                "Net loss cannot be carried forward to next year for capital gains"
            )
        
        return TaxLiability(
            jurisdiction=f"{self.get_jurisdiction_name()} ({self.get_jurisdiction_code()})",
            tax_year=tax_year,
            total_realized_gain=regular_gain + crypto_short_gain + crypto_long_gain,
            taxable_gain=taxable_gain_after_allowance,
            tax_owed=total_tax,
            breakdown=breakdown,
            notes=" | ".join(notes) if notes else None,
            assumptions=assumptions,
            calculation_date=date.today(),
            calculator_version="1.0-DE"
        )
    
    def _is_crypto(self, event: TaxEvent) -> bool:
        """
        Determine if an event is a cryptocurrency transaction.
        
        Args:
            event: Tax event to check
            
        Returns:
            True if crypto, False otherwise
        """
        # Check asset_type field
        if event.asset_type and event.asset_type.upper() == "CRYPTO":
            return True
        
        # Check ticker for common crypto symbols
        crypto_tickers = {"BTC", "ETH", "USDT", "BNB", "XRP", "ADA", "SOL", "DOGE"}
        if event.ticker and event.ticker.upper() in crypto_tickers:
            return True
        
        return False
    
    def _create_zero_liability(
        self,
        tax_year: int,
        allowance: Decimal,
        include_solidarity: bool
    ) -> TaxLiability:
        """
        Create a zero-liability result when no events exist.
        
        Args:
            tax_year: Tax year
            allowance: Allowance amount
            include_solidarity: Whether solidarity is included
            
        Returns:
            TaxLiability with zero values
        """
        assumptions = [
            f"Capital gains tax rate: {self.CAPITAL_GAINS_TAX_RATE * 100}%",
            f"Annual tax-free allowance: €{allowance:,.2f}",
        ]
        
        if include_solidarity:
            assumptions.append(
                f"Solidarity surcharge: {self.SOLIDARITY_SURCHARGE_RATE * 100}% of tax"
            )
        
        return TaxLiability(
            jurisdiction=f"{self.get_jurisdiction_name()} ({self.get_jurisdiction_code()})",
            tax_year=tax_year,
            total_realized_gain=Decimal(0),
            taxable_gain=Decimal(0),
            tax_owed=Decimal(0),
            breakdown={
                "total_realized_gain": Decimal(0),
                "taxable_gain_after_allowance": Decimal(0),
                "capital_gains_tax_25pct": Decimal(0),
                "solidarity_surcharge_5_5pct": Decimal(0),
                "total_tax_owed": Decimal(0),
            },
            notes="No taxable events in this period",
            assumptions=assumptions,
            calculation_date=date.today(),
            calculator_version="1.0-DE"
        )
