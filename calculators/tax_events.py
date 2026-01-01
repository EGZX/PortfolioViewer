"""
Tax Event and Lot Data Models

Defines the core data structures for tax basis tracking:
- TaxLot: Represents a specific purchase (acquisition)
- TaxEvent: Represents a taxable sale event
- TaxLiability: Represents calculated tax owed for a period

These are universal models used across all jurisdictions.

Copyright (c) 2026 Andre. All rights reserved.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, List
from enum import Enum


class LotMatchingMethod(str, Enum):
    """Supported lot matching strategies."""
    FIFO = "FIFO"
    WEIGHTED_AVERAGE = "WeightedAverage"
    SPECIFIC_ID = "SpecificID"


@dataclass
class TaxLot:
    """
    Represents a specific purchase lot for tax basis tracking.
    
    This is the atomic unit of cost basis. When a sale occurs, it must be
    matched to one or more lots to determine the realized gain/loss.
    
    Key Invariant: cost_basis_base is FIXED at acquisition time and never
    recalculated. This ensures deterministic tax calculations.
    """
    
    # Required fields (no defaults) - MUST come first
    lot_id: str
    ticker: str
    acquisition_date: date
    quantity: Decimal
    original_quantity: Decimal
    cost_basis_local: Decimal
    cost_basis_base: Decimal
    currency_original: str
    
    # Optional fields (with defaults) - MUST come after
    isin: Optional[str] = None
    asset_name: Optional[str] = None
    asset_type: str = "Stock"
    fees_base: Decimal = field(default_factory=lambda: Decimal(0))
    fx_rate_used: Decimal = field(default_factory=lambda: Decimal(1))
    fx_rate_source: str = "unknown"
    
    def remaining_cost_basis(self) -> Decimal:
        """Total cost basis remaining in this lot (cost + fees)."""
        return self.cost_basis_base + self.fees_base
    
    def average_cost_per_share(self) -> Decimal:
        """Average cost per share including fees."""
        if self.quantity == 0:
            return Decimal(0)
        return self.remaining_cost_basis() / self.quantity
    
    def is_exhausted(self) -> bool:
        """Check if lot has been fully sold."""
        return self.quantity <= 0


@dataclass
class TaxEvent:
    """
    Represents a realized taxable event (sale).
    
    This is the universal output of the Tax Basis Engine. Country-specific
    tax calculators consume these events to calculate tax liability.
    """
    
    # Required fields
    event_id: str
    ticker: str
    date_sold: date
    date_acquired: date
    quantity_sold: Decimal
    proceeds_base: Decimal
    cost_basis_base: Decimal
    realized_gain: Decimal
    holding_period_days: int
    lot_matching_method: LotMatchingMethod
    
    # Optional fields
    isin: Optional[str] = None
    asset_name: Optional[str] = None
    asset_type: str = "Stock"
    acquisition_date_range: Optional[List[date]] = None
    lot_ids_used: List[str] = field(default_factory=list)
    sale_currency: str = "EUR"
    sale_fx_rate: Decimal = field(default_factory=lambda: Decimal(1))
    sale_fx_source: str = "unknown"
    notes: Optional[str] = None
    
    def is_short_term(self, threshold_days: int = 365) -> bool:
        """Check if this is a short-term gain (US/UK style)."""
        return self.holding_period_days <= threshold_days
    
    def is_long_term(self, threshold_days: int = 365) -> bool:
        """Check if this is a long-term gain."""
        return self.holding_period_days > threshold_days


@dataclass
class TaxLiability:
    """
    Represents calculated tax owed for a specific period.
    
    This is the output of country-specific Tax Calculators.
    """
    
    jurisdiction: str
    tax_year: int
    total_realized_gain: Decimal
    taxable_gain: Decimal
    tax_owed: Decimal
    breakdown: Dict[str, Decimal]
    
    notes: Optional[str] = None
    assumptions: Optional[List[str]] = None
    calculation_date: Optional[date] = None
    calculator_version: str = "1.0"


@dataclass
class ImportResult:
    """Result of importing transactions to the transaction store."""
    
    added: int
    skipped: int
    flagged_for_review: int
    total_count: int
    errors: List[str] = field(default_factory=list)


@dataclass
class DuplicateWarning:
    """Represents a potential duplicate transaction pair."""
    
    transaction_a: 'Transaction'  # Forward reference
    transaction_b: 'Transaction'
    similarity_score: float
    differences: Dict[str, tuple]
    recommendation: str
