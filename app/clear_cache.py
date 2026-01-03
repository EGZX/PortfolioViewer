"""
Emergency Cache Clear Script

Clears all Streamlit caches to force recalculation with fixed ticker/ISIN logic.
Run this after deploying the ISIN/ticker bug fixes.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

st.set_page_config(page_title="Cache Clear", page_icon="🗑️")

st.title("🗑️ Cache Clear Utility")
st.warning("⚠️ This will clear ALL cached data and force recalculation of tax events and performance history.")

if st.button("Clear All Caches", type="primary"):
    st.cache_data.clear()
    st.success("✅ All caches cleared!")
    st.info("Please return to the main app and refresh to recalculate with fixed logic.")
    
st.markdown("---")
st.markdown("### Why clear cache?")
st.markdown("""
The recent bug fixes changed how assets are tracked:
- **Portfolio**: Now strictly uses ticker (no ISIN fallback)
- **Tax Engine**: Now uses ticker-first priority (was ISIN-first)

Old cached data used the buggy ISIN-first logic, which caused:
- 10x overestimated realized P/L
- 557 tax events instead of ~200
- ISINs displayed instead of tickers

Clearing cache ensures all calculations use the corrected logic.
""")
