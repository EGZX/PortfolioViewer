
import yfinance as yf

tickers = ["FWRA.L", "FWRA.DE", "FWRA.AS", "FWRA.MI"]

print(f"Checking tickers: {tickers}")

for t in tickers:
    try:
        ticker = yf.Ticker(t)
        info = ticker.info
        currency = info.get('currency', 'N/A')
        price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
        print(f"{t}: Currency={currency}, Price={price}")
    except Exception as e:
        print(f"{t}: Failed - {e}")
