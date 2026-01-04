"""
Currency Lot Tracking for FX Transactions

Tracks foreign currency positions for tax-accurate FX gain/loss calculation.
Universal implementation - jurisdiction-specific fee treatment in calculators.

Copyright (c) 2026 Andre. All rights reserved.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Optional


@dataclass
class CurrencyLot:
    """
    Represents a lot of foreign currency acquired at a specific time.
    
    Similar to stock lots, but for currency positions. Tracks gross/net amounts
    and fees separately so jurisdiction-specific tax calculators can decide
    how to treat fees.
    """
    
    lot_id: str
    currency: str  # DKK, USD, CHF, etc.
    
    # Position tracking (universal - supports all jurisdictions)
    amount: Decimal  # Current position size (tracking amount)
    amount_gross: Decimal  # Original gross amount acquired
    amount_net: Decimal  # Net amount after fees deducted
    
    # Cost tracking (universal)
    cost_basis_eur: Decimal  # EUR paid to acquire this lot
    
    # Fee tracking (let calculator decide treatment per jurisdiction)
    fee_amount: Decimal = field(default_factory=lambda: Decimal(0))
    fee_currency: str = "EUR"  # Currency the fee was paid in
    
    # Metadata
    acquisition_date: date = None
    ecb_rate_at_purchase: Decimal = field(default_factory=lambda: Decimal(1))
    
    def is_exhausted(self) -> bool:
        """Check if lot is fully consumed (with dust tolerance)."""
        return self.amount <= Decimal("0.001")
    
    def __repr__(self) -> str:
        return (
            f"CurrencyLot({self.currency}, "
            f"amount={self.amount:.2f}, "
            f"cost=€{self.cost_basis_eur:.2f}, "
            f"acquired={self.acquisition_date})"
        )
