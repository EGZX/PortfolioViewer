"""Financial metrics calculations including XIRR and absolute returns."""

from datetime import datetime
from decimal import Decimal
from typing import List, Tuple, Optional
import numpy as np
from scipy.optimize import newton

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


def xirr(dates: List[datetime], amounts: List[float], guess: float = 0.1) -> Optional[float]:
    """
    Calculate XIRR (Extended Internal Rate of Return) using Newton-Raphson method.
    
    XIRR is the annualized rate of return that makes the NPV of all cash flows equal to zero:
    NPV = Σ(CF_i / (1 + r)^((date_i - date_0).days / 365)) = 0
    
    Args:
        dates: List of transaction dates (must be sorted)
        amounts: List of cash flow amounts (negative for investments, positive for returns)
        guess: Initial guess for the rate (default: 0.1 = 10%)
    
    Returns:
        Annualized return as decimal (e.g., 0.15 for 15%), or None if calculation fails
    
    Raises:
        ValueError: If dates and amounts have different lengths or invalid cash flow pattern
    """
    if len(dates) != len(amounts):
        raise ValueError(f"Dates and amounts must have same length: {len(dates)} != {len(amounts)}")
    
    if len(dates) < 2:
        logger.warning("XIRR requires at least 2 cash flows (investment + liquidation)")
        return None
    
    # Check for valid cash flow pattern (at least one positive and one negative)
    has_negative = any(amt < 0 for amt in amounts)
    has_positive = any(amt > 0 for amt in amounts)
    
    if not (has_negative and has_positive):
        logger.warning("XIRR requires both positive and negative cash flows")
        return None
    
    # Convert to numpy arrays
    dates_np = np.array(dates)
    amounts_np = np.array(amounts, dtype=float)
    
    # Calculate days from first transaction
    base_date = dates_np[0]
    days = np.array([(d - base_date).days / 365.0 for d in dates_np])
    
    def npv(rate: float) -> float:
        """Net Present Value at given rate."""
        return np.sum(amounts_np / ((1.0 + rate) ** days))
    
    def npv_derivative(rate: float) -> float:
        """Derivative of NPV with respect to rate."""
        return np.sum(-days * amounts_np / ((1.0 + rate) ** (days + 1)))
    
    try:
        # Use Newton-Raphson method to find rate where NPV = 0
        result = newton(
            func=npv,
            x0=guess,
            fprime=npv_derivative,
            maxiter=100,
            tol=1e-6
        )
        
        # Sanity check: rate should be reasonable (-100% to +1000%)
        if -0.99 <= result <= 10.0:
            logger.info(f"XIRR calculated: {result * 100:.2f}%")
            return float(result)
        else:
            logger.warning(f"XIRR result outside reasonable range: {result * 100:.2f}%")
            return None
            
    except (RuntimeError, ValueError) as e:
        logger.warning(f"XIRR calculation did not converge: {e}")
        return None


def calculate_absolute_return(
    total_invested: Decimal,
    total_withdrawn: Decimal,
    current_value: Decimal
) -> Tuple[Decimal, Decimal]:
    """
    Calculate absolute return and return percentage.
    
    Formula:
        Absolute Return = (Current Value + Total Withdrawn) - Total Invested
        Return % = (Absolute Return / Total Invested) × 100
    
    Args:
        total_invested: Total amount invested (sum of all negative cash flows)
        total_withdrawn: Total amount withdrawn (sum of all positive cash flows excluding final valuation)
        current_value: Current portfolio value (holdings + cash)
    
    Returns:
        Tuple of (absolute_return, return_percentage)
    """
    if total_invested == 0:
        logger.warning("Cannot calculate return percentage with zero investment")
        return Decimal(0), Decimal(0)
    
    absolute_return = current_value + total_withdrawn - total_invested
    return_pct = (absolute_return / total_invested) * 100
    
    logger.info(f"Absolute return: €{absolute_return:.2f} ({return_pct:.2f}%)")
    
    return absolute_return, return_pct


def time_weighted_return(
    dates: List[datetime],
    portfolio_values: List[float],
    external_cash_flows: List[float]
) -> Optional[float]:
    """
    Calculate Time-Weighted Return (TWR) for comparison with XIRR.
    
    TWR eliminates the effect of cash flows and measures pure investment performance.
    This is optional and more complex - not implementing for MVP.
    
    Args:
        dates: List of dates for portfolio snapshots
        portfolio_values: Portfolio value at each date
        external_cash_flows: External cash flows at each date
    
    Returns:
        Annualized time-weighted return
    """
    # TODO: Implement if needed for advanced metrics
    logger.info("Time-weighted return not yet implemented")
    return None
