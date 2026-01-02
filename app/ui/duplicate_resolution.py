"""
Interactive Duplicate Review UI Component

Streamlit component for reviewing and resolving near-duplicate transactions.

Copyright (c) 2026 Andre. All rights reserved.
"""

import streamlit as st
from typing import List, Dict
from decimal import Decimal

from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


def render_duplicate_review(duplicate_groups: List[Dict], store) -> None:
    """
    Render interactive duplicate review interface.
    
    Args:
        duplicate_groups: List of duplicate groups from TransactionStore
        store: TransactionStore instance for resolving duplicates
    """
    if not duplicate_groups:
        st.info("✅ No pending duplicates found!")
        return
    
    st.warning(f"⚠️ **{len(duplicate_groups)} Potential Duplicate Groups Found**", icon="⚠️")
    st.caption("Review transactions that may be duplicates or transfers between accounts.")
    
    # Pagination
    if 'dup_review_index' not in st.session_state:
        st.session_state.dup_review_index = 0
    
    current_index = st.session_state.dup_review_index
    current_group = duplicate_groups[current_index]
    
    # Group header
    st.divider()
    cols = st.columns([2, 1, 1])
    with cols[0]:
        st.subheader(f"Group {current_index + 1} of {len(duplicate_groups)}")
    with cols[1]:
        group_type = current_group['group_type']
        if group_type == 'duplicate':
            st.markdown("**Type:** 🔄 Duplicate")
        elif group_type == 'transfer':
            st.markdown("**Type:** ↔️ Transfer")
        else:
            st.markdown(f"**Type:** {group_type}")
    with cols[2]:
        avg_score = sum(c['similarity_score'] for c in current_group['candidates']) / len(current_group['candidates'])
        confidence = "High" if avg_score >= 85 else "Medium" if avg_score >= 70 else "Low"
        st.markdown(f"**Confidence:** {confidence} ({avg_score:.0f}%)")
    
    # Display candidates
    st.markdown("### Candidate Transactions")
    
    for i, candidate in enumerate(current_group['candidates']):
        txn = candidate['transaction']
        source = candidate['source_name']
        score = candidate['similarity_score']
        
        with st.expander(f"**Transaction {i+1}: {source}** (Score: {score:.1f}%)", expanded=True):
            cols = st.columns(4)
            
            with cols[0]:
                st.markdown(f"**Date:** {txn.date}")
                st.markdown(f"**Type:** {txn.type.value}")
            
            with cols[1]:
                st.markdown(f"**Asset:** {txn.name or txn.ticker}")
                if txn.isin:
                    st.caption(f"ISIN: {txn.isin}")
            
            with cols[2]:
                st.markdown(f"**Shares:** {txn.shares}")
                st.markdown(f"**Price:** €{txn.price:.4f}")
            
            with cols[3]:
                st.markdown(f"**Total:** €{txn.total:.2f}")
                st.markdown(f"**Fees:** €{txn.fees:.2f}")
    
    # Resolution options
    st.markdown("### Resolution")
    
    if group_type == 'transfer':
        st.info("💡 **Opposite directions detected** - This appears to be a transfer between accounts, not a duplicate.")
        resolution = st.radio(
            "Action:",
            options=[
                "keep_all",
                "ignore"
            ],
            format_func=lambda x: {
                "keep_all": "✅ Keep both (not duplicates - this is a transfer)",
                "ignore": "👁️ Ignore this group (review later)"
            }[x],
            key=f"resolution_{current_group['group_id']}"
        )
    else:
        # True duplicates
        resolution = st.radio(
            "Action:",
            options=[
                "keep_first",
                *[f"keep_{i}" for i in range(len(current_group['candidates']))],
                "keep_all"
            ],
            format_func=lambda x: {
                "keep_first": "🏆 Keep most complete (highest score)",
                **{f"keep_{i}": f"📌 Keep Transaction {i+1} ({current_group['candidates'][i]['source_name']})" 
                   for i in range(len(current_group['candidates']))},
                "keep_all": "✅ Keep all (not duplicates)"
            }[x],
            key=f"resolution_{current_group['group_id']}"
        )
    
    # Navigation and action buttons
    st.divider()
    nav_cols = st.columns([1, 1, 1, 2])
    
    with nav_cols[0]:
        if st.button("◀ Previous", disabled=(current_index == 0)):
            st.session_state.dup_review_index -= 1
            st.rerun()
    
    with nav_cols[1]:
        if st.button("Next ▶", disabled=(current_index == len(duplicate_groups) - 1)):
            st.session_state.dup_review_index += 1
            st.rerun()
    
    with nav_cols[2]:
        if st.button("✓ Apply & Next", type="primary"):
            # Apply resolution
            success = _apply_resolution(
                store,
                current_group,
                resolution
            )
            
            if success:
                st.success(f"✓ Resolved group {current_index + 1}")
                
                # Move to next group if available
                if current_index < len(duplicate_groups) - 1:
                    st.session_state.dup_review_index += 1
                else:
                    st.session_state.dup_review_index = 0
                
                st.rerun()
            else:
                st.error("Failed to apply resolution")
    
    with nav_cols[3]:
        st.caption(f"Progress: {current_index + 1}/{len(duplicate_groups)}")


def _apply_resolution(store, group: Dict, resolution: str) -> bool:
    """
    Apply the selected resolution strategy.
    
    Args:
        store: TransactionStore instance
        group: Duplicate group dict
        resolution: Resolution strategy string
    
    Returns:
        True if successful
    """
    group_id = group['group_id']
    
    try:
        if resolution == 'keep_all':
            # Mark as not duplicates
            return store.resolve_duplicate_group(group_id, 'keep_all')
        
        elif resolution == 'keep_first':
            # Keep highest scoring candidate
            return store.resolve_duplicate_group(group_id, 'keep_first')
        
        elif resolution.startswith('keep_'):
            # Keep specific transaction
            index = int(resolution.split('_')[1])
            txn_id = group['candidates'][index]['transaction_id']
            return store.resolve_duplicate_group(
                group_id,
                'keep_specific',
                keep_transaction_id=txn_id
            )
        
        elif resolution == 'ignore':
            # Don't change anything this time
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error applying resolution: {e}")
        return False
