"""Test crypto price fetching"""
import sys
sys.path.insert(0, 'c:\\Users\\Andre\\PycharmProjects\\PortfolioViewer')

from lib.crypto_prices import get_crypto_price, get_crypto_prices_batch

print("Testing individual crypto price fetch:")
print("=" * 60)

btc_price = get_crypto_price('BTC', 'EUR')
eth_price = get_crypto_price('ETH', 'EUR')
sol_price = get_crypto_price('SOL', 'EUR')

if btc_price:
    print(f"BTC: EUR{btc_price:,.2f}")
if eth_price:
    print(f"ETH: EUR{eth_price:,.2f}")
if sol_price:
    print(f"SOL: EUR{sol_price:,.2f}")

print("\nTesting batch fetch:")
print("=" * 60)

prices = get_crypto_prices_batch(['BTC', 'ETH', 'SOL'], 'EUR')
for ticker, price in prices.items():
    if price:
        print(f"{ticker}: EUR{price:,.2f}")

# Calculate portfolio value
print("\nPortfolio crypto value:")
print("=" * 60)
btc_qty = 0.0495
eth_qty = 0.44799762
sol_qty = 7.85825

if btc_price and eth_price and sol_price:
    btc_val = btc_qty * btc_price
    eth_val = eth_qty * eth_price
    sol_val = sol_qty * sol_price
    total = btc_val + eth_val + sol_val
    
    print(f"BTC: {btc_qty} x EUR{btc_price:,.2f} = EUR{btc_val:,.2f}")
    print(f"ETH: {eth_qty} x EUR{eth_price:,.2f} = EUR{eth_val:,.2f}")
    print(f"SOL: {sol_qty} x EUR{sol_price:,.2f} = EUR{sol_val:,.2f}")
    print(f"\nTotal crypto value: EUR{total:,.2f}")
    print(f"Broker shows: EUR5,863.56")
    print(f"Difference: EUR{total - 5863.56:,.2f}")
