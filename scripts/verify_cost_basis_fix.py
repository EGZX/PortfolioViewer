"""
Verification script to demonstrate the cost basis fix with actual transaction data.
This script loads real transactions and shows cost basis before/after Dec 9, 2025.
"""
import sys
from decimal import Decimal
from datetime import datetime, date
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.viewer.transaction_store import TransactionStore
from modules.viewer.portfolio import Portfolio

def main():
    print("=" * 100)
    print("COST BASIS VERIFICATION - Dec 9, 2025 Fix")
    print("=" * 100)
    
    # Load transactions from database
    print("\nLoading transactions from database...")
    store = TransactionStore('data/transactions.db')
    all_transactions = store.get_all()
    print(f"Loaded {len(all_transactions)} transactions")
    
    # Filter transactions up to Dec 8, 2025
    dec_8_transactions = [t for t in all_transactions if t.date.date() <= date(2025, 12, 8)]
    print(f"\nTransactions up to Dec 8, 2025: {len(dec_8_transactions)}")
    
    # Create portfolio up to Dec 8
    portfolio_dec8 = Portfolio(dec_8_transactions)
    cost_basis_dec8 = sum(pos.cost_basis for pos in portfolio_dec8.holdings.values())
    
    print(f"Cost Basis as of Dec 8, 2025: EUR {cost_basis_dec8:,.2f}")
    
    # Filter transactions up to Dec 9, 2025
    dec_9_transactions = [t for t in all_transactions if t.date.date() <= date(2025, 12, 9)]
    print(f"\nTransactions up to Dec 9, 2025: {len(dec_9_transactions)}")
    
    # Find CASH and FX transfers on Dec 9
    dec_9_only = [t for t in all_transactions if t.date.date() == date(2025, 12, 9)]
    cash_transfers = [t for t in dec_9_only if t.ticker and (t.ticker.upper() == 'CASH' or '.' in t.ticker)]
    
    print(f"\nDec 9, 2025 CASH/FX TRANSFER_IN transactions:")
    total_cash_amount = Decimal(0)
    for t in cash_transfers:
        if t.type.value == 'TransferIn':
            print(f"  {t.ticker}: EUR {t.total:,.2f}")
            total_cash_amount += abs(t.total)
    print(f"  Total CASH/FX amount: EUR {total_cash_amount:,.2f}")
    
    # Create portfolio up to Dec 9
    portfolio_dec9 = Portfolio(dec_9_transactions)
    cost_basis_dec9 = sum(pos.cost_basis for pos in portfolio_dec9.holdings.values())
    
    print(f"\nCost Basis as of Dec 9, 2025: EUR {cost_basis_dec9:,.2f}")
    print(f"Change from Dec 8 to Dec 9: EUR {cost_basis_dec9 - cost_basis_dec8:,.2f}")
    
    # Check if CASH/FX positions exist
    print("\nCASH/FX Positions in portfolio:")
    for key, pos in portfolio_dec9.holdings.items():
        ticker_upper = pos.ticker.upper() if pos.ticker else ""
        if ticker_upper == 'CASH' or '.' in ticker_upper:
            print(f"  {pos.ticker}: {pos.shares} shares, Cost Basis: EUR {pos.cost_basis}")
    
    print("\n" + "=" * 100)
    print("VERIFICATION RESULTS")
    print("=" * 100)
    
    # Expected: Cost basis should NOT include CASH/FX transfer amounts
    # The change should only reflect actual stock purchases
    if abs(cost_basis_dec9 - cost_basis_dec8 - total_cash_amount) < 1:
        print("WARNING: Cost basis increased by CASH/FX amount - FIX NOT APPLIED")
        print(f"  This suggests CASH/FX transfers are still being added to cost basis")
    else:
        print("SUCCESS: Cost basis change does NOT include CASH/FX transfers")
        print(f"  CASH/FX Total: EUR {total_cash_amount:,.2f}")
        print(f"  Actual Cost Basis Change: EUR {cost_basis_dec9 - cost_basis_dec8:,.2f}")
        print(f"  Difference: EUR {(cost_basis_dec9 - cost_basis_dec8) - total_cash_amount:,.2f}")
        print("\nThe fix is working correctly!")
    
    print("=" * 100)

if __name__ == "__main__":
    main()
