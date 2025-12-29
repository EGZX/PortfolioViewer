"""
Generate an encryption key for the market data cache.

Run this script once and add the key to your .streamlit/secrets.toml file.
"""

from cryptography.fernet import Fernet

# Generate a new encryption key
key = Fernet.generate_key()

print("=" * 60)
print("Market Cache Encryption Key Generated")
print("=" * 60)
print()
print("Add this line to your .streamlit/secrets.toml file:")
print()
print(f'MARKET_CACHE_ENCRYPTION_KEY = "{key.decode()}"')
print()
print("=" * 60)
print()
print("IMPORTANT: Keep this key secret and DO NOT commit it to git!")
print("The .streamlit/secrets.toml file is already in .gitignore.")
print()
