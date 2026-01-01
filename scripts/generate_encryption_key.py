"""
Utility script to generate encryption keys for TransactionStore

Run this once to generate a secure encryption key for your secrets.toml

Copyright (c) 2026 Andre. All rights reserved.
"""

from cryptography.fernet import Fernet

def generate_key():
    """Generate a new Fernet encryption key."""
    key = Fernet.generate_key()
    return key.decode()

if __name__ == "__main__":
    key = generate_key()
    
    print("=" * 70)
    print("ENCRYPTION KEY FOR TRANSACTION STORE")
    print("=" * 70)
    print()
    print("Add this to your .streamlit/secrets.toml file:")
    print()
    print("[passwords]")
    print(f'TRANSACTION_STORE_ENCRYPTION_KEY = "{key}"')
    print()
    print("=" * 70)
    print("WARNING: Keep this key secure!")
    print("   - Do NOT commit it to version control")
    print("   - Back it up securely")
    print("   - Loss of key = loss of data access")
    print("=" * 70)
