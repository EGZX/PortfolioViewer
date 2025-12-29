"""
Bulk ISIN to Ticker Resolution Helper

This script:
1. Extracts all unique ISINs from your uploaded CSV
2. Attempts to resolve them using OpenFIGI
3. Generates a ready-to-paste TICKER_OVERRIDES dictionary

Usage:
    python resolve_all_isins.py path/to/your/portfolio.csv
"""

import sys
import pandas as pd
from pathlib import Path
from services.openfigi_resolver import get_openfigi_resolver
from utils.logging_config import setup_logger

logger = setup_logger(__name__)


def extract_isins_from_csv(csv_path: str) -> list[str]:
    """Extract all unique ISINs from a portfolio CSV."""
    try:
        # Try different delimiters
        for delimiter in [';', ',', '\t']:
            try:
                df = pd.read_csv(csv_path, delimiter=delimiter, encoding='utf-8')
                # Look for ISIN column (various names)
                isin_cols = [col for col in df.columns if 'isin' in col.lower() or 'identifier' in col.lower()]
                
                if isin_cols:
                    # Get all unique non-null ISINs
                    isins = df[isin_cols[0]].dropna().unique().tolist()
                    # Filter to valid ISIN format (12 characters)
                    isins = [isin for isin in isins if isinstance(isin, str) and len(isin) == 12]
                    if isins:
                        logger.info(f"Found {len(isins)} unique ISINs in column '{isin_cols[0]}'")
                        return isins
            except Exception:
                continue
        
        logger.error("Could not find ISIN column in CSV")
        return []
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        return []


def resolve_all(isins: list[str]) -> dict[str, str]:
    """Resolve all ISINs and return successful mappings."""
    resolver = get_openfigi_resolver()
    
    print("\n" + "=" * 70)
    print("Resolving ISINs via OpenFIGI...")
    print("=" * 70)
    print(f"Total ISINs to resolve: {len(isins)}")
    print(f"Estimated time: ~{len(isins) * 2.5 / 60:.1f} minutes")
    print("=" * 70)
    print()
    
    successful = {}
    failed = []
    
    for i, isin in enumerate(isins, 1):
        print(f"[{i}/{len(isins)}] Resolving {isin}...", end=' ')
        
        ticker = resolver.resolve_isin(isin)
        
        if ticker:
            successful[isin] = ticker
            print(f"✓ {ticker}")
        else:
            failed.append(isin)
            print("✗ Not found")
    
    return successful, failed


def generate_override_code(mappings: dict[str, str]) -> str:
    """Generate Python code for TICKER_OVERRIDES dictionary."""
    lines = ["# Auto-generated ISIN to Ticker mappings from OpenFIGI"]
    lines.append("# Add these to TICKER_OVERRIDES in services/market_data.py")
    lines.append("")
    lines.append("TICKER_OVERRIDES = {")
    
    for isin, ticker in sorted(mappings.items()):
        lines.append(f"    '{isin}': '{ticker}',")
    
    lines.append("}")
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python resolve_all_isins.py <path_to_csv>")
        print()
        print("Example:")
        print("  python resolve_all_isins.py portfolio.csv")
        return
    
    csv_path = sys.argv[1]
    
    if not Path(csv_path).exists():
        print(f"Error: File not found: {csv_path}")
        return
    
    # Extract ISINs
    print(f"Reading CSV: {csv_path}")
    isins = extract_isins_from_csv(csv_path)
    
    if not isins:
        print("No ISINs found in CSV")
        return
    
    # Resolve all
    successful, failed = resolve_all(isins)
    
    # Print summary
    print()
    print("=" * 70)
    print("RESOLUTION SUMMARY")
    print("=" * 70)
    print(f"✓ Successfully resolved: {len(successful)}/{len(isins)}")
    print(f"✗ Failed to resolve: {len(failed)}/{len(isins)}")
    print("=" * 70)
    print()
    
    if successful:
        # Generate code
        code = generate_override_code(successful)
        
        # Save to file
        output_file = "isin_ticker_mappings.py"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        print(f"✓ Saved mappings to: {output_file}")
        print()
        print("To use these mappings:")
        print("1. Open services/market_data.py")
        print("2. Copy the TICKER_OVERRIDES dictionary from isin_ticker_mappings.py")
        print("3. Paste it into the TICKER_OVERRIDES section (merge with existing)")
        print()
    
    if failed:
        print("Failed ISINs (add manual overrides for these):")
        for isin in failed:
            print(f"  - {isin}")
        print()


if __name__ == "__main__":
    main()
