"""Quick script to check transactions around Dec 9, 2025."""
import sqlite3
import sys

conn = sqlite3.connect('data/transactions.db')
cursor = conn.cursor()

# First check the schema
cursor.execute("PRAGMA table_info(transactions)")
columns = cursor.fetchall()
print("Database columns:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")
    
print("\n" + "="*120)
print("TRANSACTIONS AROUND DEC 9, 2025")
print("="*120)

# Query transactions
cursor.execute("""
    SELECT date, type, ticker, name, shares_enc, total_enc, fees_enc, broker 
    FROM transactions 
    WHERE date BETWEEN '2025-12-01' AND '2025-12-15' 
    ORDER BY date
""")

print(f"{'Date':<12} {'Type':<15} {'Ticker':<10} {'Name':<30} {'Shares':<12} {'Total':<15} {'Fees':<10} {'Broker':<15}")
print("-" * 120)

for row in cursor.fetchall():
    date, trans_type, ticker, name, shares, total, fees, broker = row
    ticker = ticker or ""
    name = (name or "")[:28]
    # Decrypt values if they're strings
    try:
        shares_val = float(shares) if shares else 0
    except (ValueError, TypeError):
        shares_val = 0
    try:
        total_val = float(total) if total else 0
    except (ValueError, TypeError):
        total_val = 0
    try:
        fees_val = float(fees) if fees else 0
    except (ValueError, TypeError):
        fees_val = 0
    
    print(f"{date:<12} {trans_type:<15} {ticker:<10} {name:<30} {shares_val:<12.4f} {total_val:<15.2f} {fees_val:<10.2f} {broker or '':<15}")

conn.close()
