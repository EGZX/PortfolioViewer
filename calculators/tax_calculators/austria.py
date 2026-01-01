"""
Austrian Tax Calculator (Kapitalertragsteuer - KESt)

Implements Austria's capital gains tax rules:
- 27.5% flat tax on all capital gains (stocks, crypto, bonds)
- No annual tax-free allowance
- No holding period exemptions (abolished in 2011)
- Separate reporting of gains/losses by asset type
- CRITICAL: Fees and costs CANNOT reduce taxable gains

References:
- Austrian Income Tax Act (EStG) §27a
- Eco-Social Tax Reform 2021

Copyright (c) 2026 Andre. All rights reserved.
"""

from typing import List, Dict
from decimal import Decimal
from datetime import date

from calculators.tax_events import TaxEvent, TaxLiability
from calculators.tax_calculators.base import TaxCalculator, register_calculator


@register_calculator("AT")
class AustriaTaxCalculator(TaxCalculator):
    """
    Tax calculator for Austria (Kapitalertragsteuer - KESt).
    
    Key Rules:
    - All capital gains taxed at 27.5% flat rate
    - No annual allowance (unlike Germany)
    - No holding period exemptions
    - Gains and losses reported separately by asset type
    - Fees CANNOT reduce taxable gains (unique Austrian rule)
    """
    
    # Tax rate (as of 2024)
    CAPITAL_GAINS_TAX_RATE = Decimal("0.275")  # 27.5%
    
    def get_jurisdiction_name(self) -> str:
        """Return human-readable jurisdiction name."""
        return "Austria"
    
    def get_jurisdiction_code(self) -> str:
        """Return ISO jurisdiction code."""
        return "AT"
    
    def calculate_tax_liability(
        self,
        events: List[TaxEvent],
        tax_year: int,
        **kwargs
    ) -> TaxLiability:
        """
        Calculate Austrian capital gains tax liability.
        
        Args:
            events: All tax events (will be filtered by year)
            tax_year: Calendar year for tax calculation
            **kwargs: Optional parameters (currently unused)
        
        Returns:
            TaxLiability with Austrian KESt calculation
        """
        # Filter events to tax year
        year_events = self.filter_events_by_year(events, tax_year)
        
        if not year_events:
            return self._create_zero_liability(tax_year)
        
        # Categorize events by asset type
        categorized = self._categorize_events(year_events)
        
        # Calculate gains and losses separately for each asset type
        breakdown = {}
        total_gains = Decimal(0)
        total_losses = Decimal(0)
        
        for asset_type, type_events in categorized.items():
            gains = Decimal(0)
            losses = Decimal(0)
            
            for event in type_events:
                # CRITICAL: In Austria, fees cannot reduce taxable gains
                # We use the realized_gain which should already exclude fees
                gain = event.realized_gain
                
                if gain > 0:
                    gains += gain
                else:
                    losses += abs(gain)
            
            # Store in breakdown
            breakdown[f"{asset_type}_gains"] = gains
            breakdown[f"{asset_type}_losses"] = losses
            breakdown[f"{asset_type}_net"] = gains - losses
            
            total_gains += gains
            total_losses += losses
        
        # Calculate net taxable gain
        net_taxable_gain = total_gains - total_losses
        
        # Apply 27.5% tax (only on positive net gains)
        tax_owed = Decimal(0)
        if net_taxable_gain > 0:
            tax_owed = net_taxable_gain * self.CAPITAL_GAINS_TAX_RATE
        
        # Add summary to breakdown
        breakdown["total_gains"] = total_gains
        breakdown["total_losses"] = total_losses
        breakdown["net_taxable_gain"] = net_taxable_gain
        breakdown["tax_rate"] = self.CAPITAL_GAINS_TAX_RATE
        breakdown["tax_owed"] = tax_owed
        
        # Build assumptions list
        assumptions = [
            f"Capital gains tax rate (KESt): {self.CAPITAL_GAINS_TAX_RATE * 100}%",
            "No annual tax-free allowance",
            "Fees and transaction costs do not reduce taxable gains",
            "Losses offset gains within the same tax year",
        ]
        
        # Build notes
        notes = []
        if net_taxable_gain < 0:
            notes.append(
                f"Net loss of €{abs(net_taxable_gain):,.2f} - "
                "losses can be carried forward (not implemented yet)"
            )
        
        asset_counts = {k: len(v) for k, v in categorized.items()}
        notes.append(
            f"Events by type: {', '.join(f'{k}={v}' for k, v in asset_counts.items())}"
        )
        
        return TaxLiability(
            jurisdiction=f"{self.get_jurisdiction_name()} ({self.get_jurisdiction_code()})",
            tax_year=tax_year,
            total_realized_gain=total_gains - total_losses,
            taxable_gain=net_taxable_gain,
            tax_owed=tax_owed,
            breakdown=breakdown,
            notes=" | ".join(notes) if notes else None,
            assumptions=assumptions,
            calculation_date=date.today(),
            calculator_version="1.0-AT"
        )
    
    def _categorize_events(self, events: List[TaxEvent]) -> Dict[str, List[TaxEvent]]:
        """
        Categorize events by asset type.
        
        Args:
            events: Tax events to categorize
            
        Returns:
            Dictionary mapping asset type to list of events
        """
        categorized: Dict[str, List[TaxEvent]] = {}
        
        for event in events:
            # Determine asset type
            asset_type = self._get_asset_type(event)
            
            if asset_type not in categorized:
                categorized[asset_type] = []
            
            categorized[asset_type].append(event)
        
        return categorized
    
    def _get_asset_type(self, event: TaxEvent) -> str:
        """
        Determine the asset type for categorization.
        
        Args:
            event: Tax event
            
        Returns:
            Asset type string (e.g., "Stock", "Crypto", "Bond")
        """
        # Use the asset_type field if available
        if event.asset_type:
            asset_type = event.asset_type.strip()
            if asset_type:
                return asset_type
        
        # Check ticker for crypto
        if event.ticker:
            crypto_tickers = {"BTC", "ETH", "USDT", "BNB", "XRP", "ADA", "SOL", "DOGE"}
            if event.ticker.upper() in crypto_tickers:
                return "Crypto"
        
        # Default to Stock
        return "Stock"
    
    def _create_zero_liability(self, tax_year: int) -> TaxLiability:
        """
        Create a zero-liability result when no events exist.
        
        Args:
            tax_year: Tax year
            
        Returns:
            TaxLiability with zero values
        """
        assumptions = [
            f"Capital gains tax rate (KESt): {self.CAPITAL_GAINS_TAX_RATE * 100}%",
            "No annual tax-free allowance",
        ]
        
        return TaxLiability(
            jurisdiction=f"{self.get_jurisdiction_name()} ({self.get_jurisdiction_code()})",
            tax_year=tax_year,
            total_realized_gain=Decimal(0),
            taxable_gain=Decimal(0),
            tax_owed=Decimal(0),
            breakdown={
                "total_gains": Decimal(0),
                "total_losses": Decimal(0),
                "net_taxable_gain": Decimal(0),
                "tax_owed": Decimal(0),
            },
            notes="No taxable events in this period",
            assumptions=assumptions,
            calculation_date=date.today(),
            calculator_version="1.0-AT"
        )
