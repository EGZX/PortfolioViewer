"""
Abstract Base Class for Tax Calculators

Defines the interface that all country-specific tax calculators must implement.
Each calculator takes a list of TaxEvents and produces a TaxLiability result.

Copyright (c) 2026 Andre. All rights reserved.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Type
from decimal import Decimal

from calculators.tax_events import TaxEvent, TaxLiability


class TaxCalculator(ABC):
    """
    Abstract base class for jurisdiction-specific tax calculators.
    
    Each subclass implements the tax rules for a specific country/region.
    The calculator consumes TaxEvents (universal format) and produces
    TaxLiability (jurisdiction-specific calculation).
    """
    
    @abstractmethod
    def calculate_tax_liability(
        self,
        events: List[TaxEvent],
        tax_year: int,
        **kwargs
    ) -> TaxLiability:
        """
        Calculate total tax liability for a given tax year.
        
        Args:
            events: List of realized tax events to process
            tax_year: Calendar year for tax calculation
            **kwargs: Jurisdiction-specific parameters (e.g., filing status, income)
            
        Returns:
            TaxLiability object with calculated tax owed and breakdown
        """
        pass
    
    @abstractmethod
    def get_jurisdiction_name(self) -> str:
        """
        Return the human-readable name of this tax jurisdiction.
        
        Returns:
            Jurisdiction name (e.g., "Germany", "United States")
        """
        pass
    
    @abstractmethod
    def get_jurisdiction_code(self) -> str:
        """
        Return the ISO-style code for this jurisdiction.
        
        Returns:
            Jurisdiction code (e.g., "DE", "US")
        """
        pass
    
    def filter_events_by_year(
        self,
        events: List[TaxEvent],
        tax_year: int
    ) -> List[TaxEvent]:
        """
        Filter events to only include those in the specified tax year.
        
        Args:
            events: All tax events
            tax_year: Year to filter for
            
        Returns:
            Events where date_sold falls in tax_year
        """
        return [
            event for event in events
            if event.date_sold.year == tax_year
        ]
    
    def calculate_total_gain(self, events: List[TaxEvent]) -> Decimal:
        """
        Sum up total realized gains (or losses) from events.
        
        Args:
            events: Tax events to sum
            
        Returns:
            Total realized gain (negative = loss)
        """
        return sum(
            (event.realized_gain for event in events),
            start=Decimal(0)
        )


# Registry of available calculators
_CALCULATOR_REGISTRY: Dict[str, Type[TaxCalculator]] = {}


def register_calculator(jurisdiction_code: str):
    """
    Decorator to register a tax calculator class.
    
    Usage:
        @register_calculator("DE")
        class GermanyTaxCalculator(TaxCalculator):
            ...
    """
    def decorator(cls: Type[TaxCalculator]):
        _CALCULATOR_REGISTRY[jurisdiction_code.upper()] = cls
        return cls
    return decorator


def get_calculator(jurisdiction_code: str) -> TaxCalculator:
    """
    Factory method to get a tax calculator instance.
    
    Args:
        jurisdiction_code: ISO code (e.g., "DE", "US")
        
    Returns:
        Instance of the appropriate TaxCalculator subclass
        
    Raises:
        ValueError: If jurisdiction is not supported
    """
    code = jurisdiction_code.upper()
    
    if code not in _CALCULATOR_REGISTRY:
        available = ", ".join(_CALCULATOR_REGISTRY.keys())
        raise ValueError(
            f"Tax calculator for '{jurisdiction_code}' not found. "
            f"Available: {available}"
        )
    
    calculator_class = _CALCULATOR_REGISTRY[code]
    return calculator_class()


def list_available_jurisdictions() -> List[str]:
    """
    Get list of all supported tax jurisdictions.
    
    Returns:
        List of jurisdiction codes (e.g., ["DE", "US"])
    """
    return sorted(_CALCULATOR_REGISTRY.keys())
