
# -----------------------------------------------------------------------------
# (c) 2026 Andreas Wagner. All Rights Reserved.
#
# This code is part of the Portfolio Viewer project.
# Unauthorized usage or distribution is not permitted.
# -----------------------------------------------------------------------------

import streamlit as st
from services.market_cache import get_market_cache
from services.pipeline import parse_csv_only
from utils.logging_config import setup_logger

logger = setup_logger(__name__)

def render_sidebar_controls():
    """
    Renders the top part of the sidebar: Data Import, Operations, Display Controls.
    Returns: file_content (str or None)
    """
    with st.sidebar:
        st.markdown("### DATA IMPORT")
        
        uploaded_file = st.file_uploader(
            "Import CSV",
            type=['csv'],
            label_visibility="collapsed",
            help="Upload transaction history"
        )
        
        # Cache Loading Logic
        cache = get_market_cache()
        cached_data = cache.get_last_transactions_csv()
        
        file_content = None
        filename = None
        using_cache = False

        if uploaded_file is not None:
            file_content = uploaded_file.getvalue().decode('utf-8')
            filename = uploaded_file.name
            st.caption(f"Loaded: {filename}")
            try:
                cache.save_transactions_csv(file_content, filename)
            except Exception as e:
                logger.error(f"Cache save failed: {e}")
                
        elif cached_data:
            csv_content, cache_filename, uploaded_at = cached_data
            file_content = csv_content
            filename = cache_filename
            using_cache = True
            st.caption(f"Cached: {cache_filename} | {uploaded_at.strftime('%H:%M')}")
        
        if file_content is None:
            st.info("Awaiting Data Import")
            return None

        # Session State Init
        if 'enrichment_done' not in st.session_state:
            st.session_state.enrichment_done = False
        if 'last_processed_content' not in st.session_state:
            st.session_state.last_processed_content = None
        if 'chart_view' not in st.session_state:
            st.session_state.chart_view = "Treemap"
        if 'chart_view_treemap' not in st.session_state:
            st.session_state.chart_view_treemap = True
        
        # Reset state on new file load
        if st.session_state.last_processed_content != file_content:
            st.session_state.enrichment_done = False
            st.session_state.last_processed_content = file_content
            # Auto-detect enrichment from cache
            try:
                quick_transactions, _ = parse_csv_only(file_content)
                if quick_transactions:
                    sample_isins = [t.ticker for t in quick_transactions[:10] if t.ticker and len(t.ticker) == 12]
                    if sample_isins:
                        cached_mappings = sum(1 for isin in sample_isins if cache.get_isin_mapping(isin))
                        if cached_mappings >= len(sample_isins) * 0.5:
                            st.session_state.enrichment_done = True
            except:
                pass

        st.markdown("### OPERATIONS")
        
        # Action Buttons
        col_act1, col_act2 = st.columns(2)
        
        with col_act1:
            if st.button("REFRESH", use_container_width=True):
                st.session_state.enrichment_done = False
                st.rerun()
                
        with col_act2:
            if st.button("PURGE CACHE", use_container_width=True):
                cache.clear_cache()
                st.rerun()

        st.markdown("---")
        
        # Display Controls Section
        st.markdown("### DISPLAY")
        
        # Privacy Mode Toggle
        if 'privacy_mode' not in st.session_state:
            st.session_state.privacy_mode = False
            
        privacy_mode = st.toggle("Privacy Mode", value=st.session_state.privacy_mode, help="Hide financial values")
        if privacy_mode != st.session_state.privacy_mode:
            st.session_state.privacy_mode = privacy_mode
            st.rerun()
        
        # Chart View Toggle (Treemap/Pie)
        if 'chart_view_treemap' not in st.session_state:
            st.session_state.chart_view_treemap = True
        
        chart_view_treemap = st.toggle("Treemap View", value=st.session_state.chart_view_treemap, help="Toggle between Treemap and Pie chart")
        if chart_view_treemap != st.session_state.chart_view_treemap:
            st.session_state.chart_view_treemap = chart_view_treemap
            st.session_state.chart_view = "Treemap" if chart_view_treemap else "Pie"
        
        # Mobile View Override (auto-detected but can be toggled)
        if 'is_mobile' not in st.session_state:
            st.session_state.is_mobile = False
        
        mobile_mode = st.toggle("Mobile View", value=st.session_state.is_mobile, help="Override auto-detected screen size")
        if mobile_mode != st.session_state.is_mobile:
            st.session_state.is_mobile = mobile_mode
            st.rerun()
            
        return file_content

def render_sidebar_status(transactions, tickers, prices, validation_data):
    """
    Renders the status grid at the bottom of the sidebar.
    """
    with st.sidebar:
        st.markdown("### System Status")
        
        # 2x2 Grid using columns
        row1_1, row1_2 = st.columns(2)
        row1_1.metric("TX Count", len(transactions))
        row1_2.metric("Assets", len(tickers))
        
        row2_1, row2_2 = st.columns(2)
        status_txt = "Active" if st.session_state.get('enrichment_done') else "Pending"
        row2_1.metric("Enrichment", status_txt)
        
        live_prices_count = sum(1 for p in prices.values() if p is not None)
        row2_2.metric("Market Data", f"{live_prices_count}/{len(tickers)}")

        # Validation Warnings
        if validation_data:
             _, val_summary = validation_data
             if val_summary and (val_summary['ERROR'] > 0 or val_summary['WARNING'] > 0):
                 st.warning(f"Data Issues: {val_summary['ERROR']} Errors, {val_summary['WARNING']} Warnings")
