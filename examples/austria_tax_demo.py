"""
Austrian Tax Calculator - Usage Example

Demonstrates how to use the Austrian tax calculator with sample data.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

from datetime import date
from decimal import Decimal

from calculators.tax_events import TaxEvent, LotMatchingMethod
from calculators.tax_calculators import get_calculator


def main():
    """Demonstrate Austrian tax calculator usage."""
    
    print("=" * 70)
    print("Austrian Tax Calculator (KESt) - Demo")
    print("=" * 70)
    print()
    
    # Create sample tax events
    events = [
        # Stock gain
        TaxEvent(
            event_id="STOCK-001",
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
        ),
        # Stock loss
        TaxEvent(
            event_id="STOCK-002",
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
        ),
        # Crypto gain
        TaxEvent(
            event_id="CRYPTO-001",
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
        ),
    ]
    
    # Get Austria calculator
    calculator = get_calculator("AT")
    print(f"Using calculator: {calculator.get_jurisdiction_name()} ({calculator.get_jurisdiction_code()})")
    print()
    
    # Calculate tax liability for 2024
    liability = calculator.calculate_tax_liability(events, tax_year=2024)
    
    # Display results
    print(f"Tax Year: {liability.tax_year}")
    print(f"Jurisdiction: {liability.jurisdiction}")
    print()
    
    print("=" * 70)
    print("BREAKDOWN BY ASSET TYPE")
    print("=" * 70)
    
    # Display stock breakdown
    if "Stock_gains" in liability.breakdown:
        print("\nStock Sales:")
        print(f"  Gains:  €{liability.breakdown['Stock_gains']:>12,.2f}")
        print(f"  Losses: €{liability.breakdown['Stock_losses']:>12,.2f}")
        print(f"  Net:    €{liability.breakdown['Stock_net']:>12,.2f}")
    
    # Display crypto breakdown
    if "Crypto_gains" in liability.breakdown:
        print("\nCrypto Sales:")
        print(f"  Gains:  €{liability.breakdown['Crypto_gains']:>12,.2f}")
        print(f"  Losses: €{liability.breakdown['Crypto_losses']:>12,.2f}")
        print(f"  Net:    €{liability.breakdown['Crypto_net']:>12,.2f}")
    
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total Gains:         €{liability.breakdown['total_gains']:>12,.2f}")
    print(f"Total Losses:        €{liability.breakdown['total_losses']:>12,.2f}")
    print(f"Net Taxable Gain:    €{liability.breakdown['net_taxable_gain']:>12,.2f}")
    print(f"Tax Rate:            {liability.breakdown['tax_rate'] * 100:>12.2f}%")
    print(f"Tax Owed:            €{liability.tax_owed:>12,.2f}")
    print()
    
    print("=" * 70)
    print("ASSUMPTIONS")
    print("=" * 70)
    for assumption in liability.assumptions:
        print(f"  • {assumption}")
    
    if liability.notes:
        print()
        print("=" * 70)
        print("NOTES")
        print("=" * 70)
        print(f"  {liability.notes}")
    
    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
