"""
Quick verification script to check if code changes are active.
Run this to verify the fixes are loaded.
"""

# Test 1: AssetType.normalize exists
try:
    from parsers.enhanced_transaction import AssetType
    
    # Test normalization
    test_result = AssetType.normalize("Aktien")
    
    if hasattr(AssetType, 'normalize'):
        print("[OK] AssetType.normalize() method EXISTS")
        print(f"  Test: 'Aktien' -> {test_result}")
        if test_result == AssetType.STOCK:
            print("  [OK] Normalization works correctly!")
        else:
            print(f"  [ERROR] Expected Stock, got {test_result}")
    else:
        print("[ERROR] AssetType.normalize() method NOT FOUND")
        print("  The code changes were not picked up!")
except Exception as e:
    print(f"[ERROR] loading AssetType: {e}")

print()

# Test 2: Corporate actions has date filter
try:
    import inspect
    from services.corporate_actions import CorporateActionService
    
    source = inspect.getsource(CorporateActionService.fetch_split_history)
    
    if "today" in source and "future" in source.lower():
        print("[OK] Corporate actions has future-date filter")
        if "split_date_obj > today" in source:
            print("  [OK] Date comparison logic found!")
        else:
            print("  [?] Date filter exists but format unclear")
    else:
        print("[ERROR] Future-date filter NOT FOUND in corporate_actions")
        print("  The code changes were not picked up!")
except Exception as e:
    print(f"[ERROR] loading CorporateActionService: {e}")

print()
print("=" * 60)
print("VERDICT:")
print("=" * 60)

try:
    if hasattr(AssetType, 'normalize') and AssetType.normalize("Aktien") == AssetType.STOCK:
        print("[SUCCESS] CODE CHANGES ARE ACTIVE")
        print()
        print("If the app still shows issues:")
        print("1. Streamlit is caching old data")
        print("2. Press 'C' in the Streamlit app to clear cache")
        print("3. Or restart with: streamlit run portfolio_viewer.py --server.runOnSave=true")
    else:
        print("[FAILED] CODE CHANGES NOT ACTIVE")
        print()
        print("Solutions:")
        print("1. Stop the app (Ctrl+C)")
        print("2. Delete __pycache__ directories:")
        print("   python -c \"import pathlib; [p.unlink() for p in pathlib.Path('.').rglob('*.pyc')]\"")
        print("3. Restart: streamlit run portfolio_viewer.py")
except Exception as e:
    print(f"[ERROR] VERIFICATION FAILED: {e}")
