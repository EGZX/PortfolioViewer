"""
Interactive Duplicate Review UI Component

Streamlit component for reviewing and resolving near-duplicate transactions.
Compact list view for efficiency.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import streamlit as st
from typing import List, Dict

from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


def render_duplicate_review(duplicate_groups: List[Dict], store) -> None:
    """
    Render interactive duplicate review interface (Compact List View).
    """
    if not duplicate_groups:
        st.info("✅ No pending duplicates found!")
        return
    
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.warning(f"⚠️ **{len(duplicate_groups)} Potential Duplicate Groups**", icon="⚠️")
    with col2:
        high_conf_count = sum(1 for g in duplicate_groups if _get_confidence(g) >= 95)
        if high_conf_count > 0:
            if st.button(f"🧹 Fix {high_conf_count} Exact", type="primary", width="stretch"):
                 with st.spinner("Resolving..."):
                     _bulk_resolve_exact(store, duplicate_groups)
                     st.rerun()

    # Column Headers
    st.markdown("---")
    h_cols = st.columns([0.5, 3, 2, 2.5])
    h_cols[0].caption("#")
    h_cols[1].caption("TRANSACTION (Date | Ticker | Type)")
    h_cols[2].caption("CONFLICT (Diffs)")
    h_cols[3].caption("ACTION")
    st.markdown("---")

    # Pagination
    BATCH_SIZE = 50
    current_page = st.session_state.get('dup_page', 0)
    
    start_idx = current_page * BATCH_SIZE
    end_idx = start_idx + BATCH_SIZE
    visible_groups = duplicate_groups[start_idx:end_idx]
    
    for i, group in enumerate(visible_groups):
        _render_group_row(store, group, start_idx + i + 1)
        # Removing divider to make it more table-like, just a small spacer or faint line
        st.markdown("<hr style='margin: 0.2rem 0; opacity: 0.3;'>", unsafe_allow_html=True)

    # Next/Prev
    if len(duplicate_groups) > BATCH_SIZE:
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            if st.button("◀ Prev", disabled=(current_page == 0)):
                st.session_state.dup_page = max(0, current_page - 1)
                st.rerun()
        with c2:
            st.caption(f"Page {current_page+1} of {(len(duplicate_groups)//BATCH_SIZE)+1}")
        with c3:
            if end_idx < len(duplicate_groups):
                if st.button("Next ▶"):
                    st.session_state.dup_page = current_page + 1
                    st.rerun()


def _get_confidence(group: Dict) -> float:
    candidates = group.get('candidates', [])
    if not candidates: return 0.0
    return sum(c['similarity_score'] for c in candidates) / len(candidates)


def _render_group_row(store, group: Dict, index: int):
    """Render a single group as a compact row."""
    group_id = group['group_id']
    candidates = group['candidates']
    confidence = _get_confidence(group)
    
    c1 = candidates[0]
    t1 = c1['transaction']
    c2 = candidates[1] if len(candidates) > 1 else c1
    t2 = c2['transaction']
    
    # Columns: Index | Tx Info | Diffs | Actions
    cols = st.columns([0.5, 3, 2, 2.5])
    
    # Col 1: Index
    with cols[0]:
        st.text(f"#{index}")

    # Col 2: Info
    with cols[1]:
        # Compact info with explicit A/B comparison
        # t1 info
        st.markdown(f"**{t1.ticker}** | {t1.date} | {t1.type.value}")
        
        # Show Candidate A
        # Note: Prices are now Normalized to EUR in the pipeline
        st.markdown(f"**A:** {c1['source_name']}: {t1.shares} @ {t1.price:.2f} **EUR** (orig {t1.original_currency})")
        
        # Show Candidate B
        if len(candidates) > 1:
            st.markdown(f"**B:** {c2['source_name']}: {t2.shares} @ {t2.price:.2f} **EUR** (orig {t2.original_currency})")
        else:
             st.caption("No second candidate?")

    # Col 3: Difference
    with cols[2]:
        diffs = []
        if abs(t1.shares - t2.shares) > 0.0001:
            diffs.append(f"Qty: {t1.shares:.4f} vs {t2.shares:.4f}")
        
        # Price check with currency awareness
        if t1.original_currency == t2.original_currency:
            if abs(t1.price - t2.price) > 0.01:
                 diffs.append(f"Px: {t1.price:.2f} vs {t2.price:.2f}")
        else:
            diffs.append(f"Curr: {t1.original_currency} vs {t2.original_currency}")
            diffs.append(f"Px: {t1.price:.2f} vs {t2.price:.2f}")
            
        if diffs:
            for d in diffs:
                st.markdown(f"**{d}**")
        else:
            st.caption("Identical")

    # Col 4: Actions
    with cols[3]:
        # Compact buttons
        # Key: btn_{action}_{index}_{group_id} to ensure uniqueness
        
        # We assume c1 is usually the "old" one (generic import) and c2 is "new" (IBKR PQ.csv)
        # But we can't be sure without checking source names.
        
        # Let's try to identify which is 'better'
        c1_clean = c1['source_name'].replace('.csv', '')
        c2_clean = c2['source_name'].replace('.csv', '')
        
        b1, b2, b3 = st.columns([1, 1, 0.8])
        
        with b1:
            # Keep A
            if st.button(f"Keep A", key=f"k1_{group_id}", help=f"Keep {c1['source_name']}"):
                _resolve_keep_specific(store, group_id, c1['transaction_id'])
                st.rerun()
        
        with b2:
            # Keep B
            if st.button(f"Keep B", key=f"k2_{group_id}", help=f"Keep {c2['source_name']}"):
                _resolve_keep_specific(store, group_id, c2['transaction_id'])
                st.rerun()
                
        with b3:
            # Ignore
            if st.button("Ignore", key=f"ig_{group_id}"):
                store.resolve_duplicate_group(group_id, 'keep_all')
                st.rerun()


def _resolve_keep_specific(store, group_id, transaction_id):
    try:
        store.resolve_duplicate_group(group_id, 'keep_specific', keep_transaction_id=transaction_id)
    except Exception as e:
        logger.error(f"Resolution failed: {e}")
        st.error(f"Error: {e}")


def _bulk_resolve_exact(store, groups):
    count = 0
    with st.status("Resolving...") as status:
        for g in groups:
            if _get_confidence(g) >= 95:
                # Prefer source with 'PQ' or 'interactive'
                candidates = g.get('candidates', [])
                preferred_id = None
                for c in candidates:
                    src = c['source_name'].lower()
                    if 'pq' in src or 'interactive' in src:
                        preferred_id = c['transaction_id']
                        break
                
                if preferred_id:
                    store.resolve_duplicate_group(g['group_id'], 'keep_specific', keep_transaction_id=preferred_id)
                else:
                    store.resolve_duplicate_group(g['group_id'], 'keep_first')
                count += 1
        status.update(label=f"Fixed {count} groups!", state="complete")
    
    if count > 0:
        st.success(f"Resolved {count} groups!")
