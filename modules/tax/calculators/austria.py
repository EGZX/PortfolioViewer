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

from modules.tax.tax_events import TaxEvent, TaxLiability
from modules.tax.calculators.base import TaxCalculator, register_calculator


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
        Calculate Austrian capital gains tax liability (E1kv compliant).
        Mappings to E1kv 2018+ Kennzahlen (Kz) for FOREIGN income (standard for self-reporting).
        
        Kz Buckets:
        - 863: Dividends, Interest (Stocks/Bonds)
        - 898: Fund Distributions (ETFs/Funds)
        - 994: Realized Gains (Stocks/Funds/Bonds)
        - 892: Realized Losses (Stocks/Funds/Bonds)
        - 995: Derivative Gains
        - 896: Derivative Losses
        
        FX Gains are inherently calculated day-accurately via the TaxEvent proceeds/cost in EUR.
        """
        # Filter events to tax year
        year_events = self.filter_events_by_year(events, tax_year)
        
        if not year_events:
            return self._create_zero_liability(tax_year)
        
        # Split into Foreign (E1kv - Untaxed) and Domestic (Endbesteuert - Taxed)
        # Using 0.01 threshold to avoid float dust
        year_events_foreign = [e for e in year_events if e.tax_already_paid < Decimal('0.01')]
        year_events_domestic = [e for e in year_events if e.tax_already_paid >= Decimal('0.01')]
        
        # Initialize Pots (Foreign Only for E1kv)
        pots = {
            "kz_863": Decimal(0), # Dividends/Interest
            "kz_898": Decimal(0), # Fund Distributions
            "kz_994": Decimal(0), # Realized Gains
            "kz_892": Decimal(0), # Realized Losses
            "kz_995": Decimal(0), # Derivative Gains
            "kz_896": Decimal(0), # Derivative Losses
        }
        
        total_gains = Decimal(0)
        total_losses = Decimal(0)
        
        fund_types = {"ETF", "FUND", "MUTUALFUND"}
        deriv_types = {"OPTION", "FUTURE", "CFD", "WARRANT"}
        
        # Process Foreign (Untaxed) Events for E1kv
        for event in year_events_foreign:
            amount = event.realized_gain
            asset_type_upper = event.asset_type.upper() if event.asset_type else "STOCK"
            
            # Check for Income (Dividend/Interest)
            is_income = event.quantity_sold == 0
            
            if is_income:
                # Income Event
                if asset_type_upper in fund_types:
                    pots["kz_898"] += amount # Fund Distributions
                else:
                    pots["kz_863"] += amount # Stock/Bond Dividends/Interest
                
                total_gains += amount
                
            else:
                # Sale Event
                is_deriv = asset_type_upper in deriv_types
                
                if is_deriv:
                    if amount >= 0:
                        pots["kz_995"] += amount
                        total_gains += amount
                    else:
                        loss = abs(amount)
                        pots["kz_896"] += loss
                        total_losses += loss
                else:
                    if amount >= 0:
                        pots["kz_994"] += amount
                        total_gains += amount
                    else:
                        loss = abs(amount)
                        pots["kz_892"] += loss
                        total_losses += loss
        
        # Process Domestic (Taxed) Events for Information
        domestic_gains = sum(e.realized_gain for e in year_events_domestic if e.realized_gain > 0)
        domestic_losses = sum(abs(e.realized_gain) for e in year_events_domestic if e.realized_gain < 0)
        domestic_tax_paid = sum(e.tax_already_paid for e in year_events_domestic)
                        
        # Netting per § 27 Abs 8 EStG (Foreign Only)
        net_taxable_gain = total_gains - total_losses
        
        # Calculate Tax (27.5%)
        tax_owed = Decimal(0)
        if net_taxable_gain > 0:
            tax_owed = net_taxable_gain * self.CAPITAL_GAINS_TAX_RATE
            
        # Breakdown for Report
        breakdown = {
            "Kz 863 (Dividends/Interest Foreign)": pots["kz_863"],
            "Kz 898 (Fund Distributions Foreign)": pots["kz_898"],
            "Kz 994 (Realized Gains Foreign)": pots["kz_994"],
            "Kz 892 (Realized Losses Foreign)": pots["kz_892"],
            "Kz 995 (Derivative Gains Foreign)": pots["kz_995"],
            "Kz 896 (Derivative Losses Foreign)": pots["kz_896"],
            "total_gains": total_gains,
            "total_losses": total_losses,
            "net_taxable_gain": net_taxable_gain,
            "tax_rate": self.CAPITAL_GAINS_TAX_RATE,
            "tax_owed": tax_owed,
            # Domestic Info
            "domestic_income_gross": domestic_gains - domestic_losses,
            "domestic_tax_withheld": domestic_tax_paid
        }
        
        assumptions = [
            f"Capital gains tax rate (KESt): {self.CAPITAL_GAINS_TAX_RATE * 100}%",
            "Report maps to Form E1kv (Foreign Income/Auslandsdepot) ONLY",
            f"Excluded {len(year_events_domestic)} domestic transactions where tax was already withheld (Endbesteuert)",
            "Losses offset gains within the same tax year (Foreign bucket)",
            "FX gains calculated day-accurately on transaction dates"
        ]
        
        notes = []
        if net_taxable_gain < 0:
            notes.append(f"Net Loss of €{abs(net_taxable_gain):,.2f} remaining.")
            
        return TaxLiability(
            jurisdiction=f"{self.get_jurisdiction_name()} ({self.get_jurisdiction_code()}) - E1kv",
            tax_year=tax_year,
            total_realized_gain=net_taxable_gain, # Net economic gain
            taxable_gain=net_taxable_gain, # Taxable base
            tax_owed=tax_owed,
            breakdown=breakdown,
            notes=" | ".join(notes) if notes else None,
            assumptions=assumptions,
            calculation_date=date.today(),
            calculator_version="2.0-AT-E1kv"
        )

    def _create_zero_liability(self, tax_year: int) -> TaxLiability:
        """Create zero liability."""
        return TaxLiability(
            jurisdiction=f"{self.get_jurisdiction_name()} ({self.get_jurisdiction_code()})",
            tax_year=tax_year,
            total_realized_gain=Decimal(0),
            taxable_gain=Decimal(0),
            tax_owed=Decimal(0),
            breakdown={k: Decimal(0) for k in ["total_gains", "total_losses", "net_taxable_gain", "tax_owed"]},
            notes="No taxable events",
            assumptions=[],
            calculation_date=date.today(),
            calculator_version="2.0-AT-E1kv"
        )
