"""
Tax Calculator System

Provides country-specific tax calculation implementations for capital gains.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

from .base import TaxCalculator, get_calculator
from .austria import AustriaTaxCalculator

__all__ = [
    "TaxCalculator",
    "AustriaTaxCalculator",
    "get_calculator",
]

