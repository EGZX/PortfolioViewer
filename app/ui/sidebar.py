
# -----------------------------------------------------------------------------
# (c) 2026 Andreas Wagner. All Rights Reserved.
#
# This code is part of the Portfolio Viewer project.
# Unauthorized usage or distribution is not permitted.
# -----------------------------------------------------------------------------

import streamlit as st
from lib.market_cache import get_market_cache
from lib.pipeline import parse_csv_only, process_data_pipeline
from modules.viewer.transaction_store import TransactionStore
from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)

def render_sidebar_controls():
    """
    Renders the top part of the sidebar: Data Import, Operations, Display Controls.
    Returns: file_content (str or None)
    """
    with st.sidebar:
        st.markdown("### DATA IMPORT")
        
        # Initialize multi-source mode state
        if 'use_multi_source' not in st.session_state:
            st.session_state.use_multi_source = True
        
        # Mode toggle
        multi_source_mode = st.toggle(
            "Multi-Source Mode",
            value=st.session_state.use_multi_source,
            help="Enable persistent storage for multiple broker accounts"
        )
        
        if multi_source_mode != st.session_state.use_multi_source:
            st.session_state.use_multi_source = multi_source_mode
            st.rerun()
        
        # --- MULTI-SOURCE MODE ---
        if st.session_state.use_multi_source:
            try:
                store = TransactionStore()
                current_counts = store.get_transaction_count_by_source()
                uploaded_files = st.file_uploader(
                    "Upload CSV Files",
                    type=['csv'],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    help="Upload one or more transaction files"
                )
                
                if uploaded_files:
                    source_name = st.text_input(
                        "Source Name",
                        value=f"Import_{len(store.get_sources()) + 1}",
                        help="Name for this import (e.g., 'Broker_A', 'Degiro_2024')"
                    )
                    
                    if st.button("Import Files", type="primary"):
                        with st.spinner("Importing transactions..."):
                            total_added = 0
                            total_skipped = 0
                            
                            for uploaded_file in uploaded_files:
                                logger.info(f"Processing file: {uploaded_file.name}, size: {uploaded_file.size} bytes")
                                file_content = uploaded_file.getvalue().decode('utf-8')
                                logger.info(f"Decoded content length: {len(file_content)} chars")
                                
                                # Parse and enrich transactions
                                logger.info("Starting pipeline processing...")
                                transactions, _, _ = process_data_pipeline(file_content)
                                logger.info(f"Pipeline returned {len(transactions) if transactions else 0} transactions")
                                
                                if not transactions:
                                    st.error(f"Failed to parse {uploaded_file.name} - no valid transactions found")
                                    logger.error(f"Parser returned empty list for {uploaded_file.name}")
                                    continue
                                
                                # Add to store
                                result = store.append_transactions(
                                    transactions,
                                    source_name=f"{source_name}_{uploaded_file.name}",
                                    dedup_strategy="hash_first"
                                )
                                
                                total_added += result.added
                                total_skipped += result.skipped
                            
                            if total_added > 0:
                                st.success(f"✅ Added: {total_added} | Skipped: {total_skipped} (duplicates)")
                            else:
                                st.warning("No transactions were imported. Check the CSV format.")
                            st.rerun()
                
                # Show active sources
                st.markdown("#### Active Sources")
                sources = store.get_sources()
                counts = store.get_transaction_count_by_source()
                
                if sources:
                    for source in sources:
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.text(source)
                        with col2:
                            st.caption(f"{counts.get(source, 0)} tx")
                        with col3:
                            if st.button("🗑️", key=f"del_{source}", help="Delete this source"):
                                store.delete_by_source(source)
                                st.success(f"Deleted {source}")
                                st.rerun()
                else:
                    st.info("No sources imported yet")
                
                # Duplicate Detection Section
                st.divider()
                dup_count = store.get_pending_duplicate_count()
                
                if dup_count > 0:
                    st.warning(f"⚠️ **{dup_count} Potential Duplicates**", icon="⚠️")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🔍 Review", width='stretch'):
                            st.session_state.show_duplicate_review = True
                            st.rerun()
                    with col2:
                        if st.button("🔄 Scan Now", width='stretch'):
                            with st.spinner("Scanning for duplicates..."):
                                store.find_near_duplicates(min_score=60)
                            st.rerun()
                else:
                    if st.button("🔍 Scan for Duplicates", width='stretch'):
                        with st.spinner("Scanning..."):
                            groups = store.find_near_duplicates(min_score=60)
                            if groups:
                                st.success(f"Found {len(groups)} duplicate groups!")
                            else:
                                st.success("✅ No duplicates found")
                        st.rerun()
                
                # Export Merged Dataset
                st.divider()
                st.markdown("#### Export")
                
                if st.button("📥 Export Merged CSV", width='stretch'):
                    import csv
                    import io
                    from datetime import datetime
                    
                    # Get all transactions
                    transactions = store.get_all_transactions()
                    
                    if transactions:
                        # Create CSV
                        output = io.StringIO()
                        writer = csv.writer(output)
                        
                        # Header
                        writer.writerow([
                            'Date', 'Type', 'Ticker', 'ISIN', 'Name', 'Asset Type',
                            'Shares', 'Price', 'Total', 'Fees', 'Currency', 'Source'
                        ])
                        
                        # Data rows
                        for txn in transactions:
                            # Sanitize currency (use ISO code, replace symbols)
                            raw_curr = getattr(txn, 'original_currency', None) or getattr(txn, 'currency', 'EUR')
                            curr_clean = raw_curr.replace('€', 'EUR') if raw_curr else 'EUR'
                            
                            writer.writerow([
                                txn.date,
                                txn.type.value,
                                txn.ticker or '',
                                txn.isin or '',
                                txn.name or '',
                                txn.asset_type.value if txn.asset_type else '',
                                float(txn.shares),
                                float(txn.price),
                                float(txn.total),
                                float(txn.fees) if txn.fees else 0.0,
                                curr_clean,
                                txn.import_source or 'Unknown'
                            ])
                        
                        # Download button
                        csv_data = output.getvalue()
                        st.download_button(
                            label="⬇️ Download CSV",
                            data=csv_data,
                            file_name=f"merged_transactions_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            width='stretch'
                        )
                    else:
                        st.warning("No transactions to export")
                
                # Load all transactions from store for processing
                file_content = "MULTI_SOURCE_MODE"  # Marker
                
            except Exception as e:
                st.error(f"TransactionStore error: {str(e)}")
                logger.error(f"Multi-source error: {e}", exc_info=True)
                return None
        
        # --- SINGLE-FILE MODE (Legacy) ---
        else:
            uploaded_file = st.file_uploader(
                "Import CSV",
                type=['csv'],
                label_visibility="collapsed",
                help="Upload transaction history"
            )
            
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
            # Auto-detect enrichment from cache (Single File Mode only)
            if file_content != "MULTI_SOURCE_MODE":
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
            if st.button("REFRESH"):
                st.session_state.enrichment_done = False
                st.session_state.prices_updated = True
                st.rerun()
                
        with col_act2:
            if st.button("PURGE CACHE"):
                cache.clear_cache()
                st.rerun()
        
        # Historical Data Button (below action buttons)
        if st.button("📈 Fetch Historical Data", help="Load full price history for performance chart (may take 2-5 min)", type="secondary"):
            st.session_state.fetch_historical_data = True
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
