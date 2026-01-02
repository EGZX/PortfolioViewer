"""
Automated Import Update Script

Updates all import statements to reflect new directory structure:
- calculators/ → modules/viewer/ or modules/tax/
- services/ → lib/
- parsers/ → lib/parsers/
- utils/ → lib/utils/
- ui/ → app/ui/
- charts/ → app/charts/
"""

import os
import re
from pathlib import Path

# Import mapping rules
IMPORT_REPLACEMENTS = [
    # calculators → modules
    (r'from calculators\.portfolio import', 'from modules.viewer.portfolio import'),
    (r'from calculators\.metrics import', 'from modules.viewer.metrics import'),
    (r'from calculators\.tax_basis import', 'from modules.tax.engine import'),
    (r'from calculators\.tax_calculators', 'from modules.tax.calculators'),
    (r'from calculators\.tax_events import', 'from modules.tax.tax_events import'),
    (r'from calculators\.duplicate_detector import', 'from modules.viewer.duplicate_detector import'),
    (r'from calculators\.transaction_store import', 'from modules.viewer.transaction_store import'),
    
    # services → lib
    (r'from services\.market_data import', 'from lib.market_data import'),
    (r'from services\.market_cache import', 'from lib.market_data import'),  # Legacy, redirects to new
    (r'from services\.fx_rates import', 'from lib.fx_rates import'),
    (r'from services\.corporate_actions', 'from lib.corporate_actions'),
    (r'from services\.data_validator import', 'from lib.validators import'),
    (r'from services\.isin_resolver import', 'from lib.isin_resolver import'),
    (r'from services\.openfigi_resolver import', 'from lib.openfigi_resolver import'),
    (r'from services\.multi_provider import', 'from lib.multi_provider import'),
    (r'from services\.pipeline import', 'from lib.pipeline import'),
    
    # parsers → lib.parsers
    (r'from parsers\.', 'from lib.parsers.'),
    
    # utils → lib.utils
    (r'from utils\.', 'from lib.utils.'),
    
    # ui → app.ui
    (r'from ui\.', 'from app.ui.'),
    
    # charts → app.charts
    (r'from charts\.', 'from app.charts.'),
]

def update_imports_in_file(filepath):
    """Update imports in a single Python file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes_made = 0
        
        for pattern, replacement in IMPORT_REPLACEMENTS:
            new_content, count = re.subn(pattern, replacement, content)
            if count > 0:
                content = new_content
                changes_made += count
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return changes_made
        
        return 0
    
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return 0

def main():
    """Update all Python files in the project."""
    project_root = Path(__file__).parent.parent
    
    # Directories to scan
    scan_dirs = ['app', 'modules', 'lib', 'core', 'tests']
    
    total_files = 0
    total_changes = 0
    
    print("Starting import updates...")
    print("=" * 60)
    
    for dir_name in scan_dirs:
        dir_path = project_root / dir_name
        if not dir_path.exists():
            continue
        
        for py_file in dir_path.rglob('*.py'):
            changes = update_imports_in_file(py_file)
            if changes > 0:
                total_files += 1
                total_changes += changes
                print(f"[OK] {py_file.relative_to(project_root)}: {changes} changes")
    
    print("=" * 60)
    print(f"Summary: Updated {total_changes} imports in {total_files} files")

if __name__ == '__main__':
    main()
