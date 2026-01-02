"""
Import Update Script - Fix get_market_cache location

Updates imports from lib.market_data to lib.market_cache
"""

import os
import re
from pathlib import Path

# Files to update
files_to_update = [
    "app/ui/sidebar.py",
    "lib/fx_rates.py", 
    "lib/market_data.py",
    "lib/corporate_actions.py",
    "lib/validators.py",
    "lib/openfigi_resolver.py",
   "scripts/view_cache_stats.py",
    "scripts/clear_split_cache.py",
]

project_root = Path(__file__).parent.parent

for filepath in files_to_update:
    full_path = project_root / filepath
    if not full_path.exists():
        print(f"Skip: {filepath} (not found)")
        continue
    
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    updated = content.replace(
        'from lib.market_data import get_market_cache',
        'from lib.market_cache import get_market_cache'
    )
    
    if updated != content:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(updated)
        print(f"Updated: {filepath}")
    else:
        print(f"No change: {filepath}")

print("Done!")
