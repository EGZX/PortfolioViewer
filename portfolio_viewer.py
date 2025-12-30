"""
Portfolio Viewer - Streamlit Application

A production-grade portfolio analysis tool with:
- CSV transaction import with auto-format detection
- Live market data from yfinance
- XIRR and absolute return calculations
- Interactive visualizations
"""

import streamlit as st
from datetime import datetime, timedelta
from decimal import Decimal
import pandas as pd
import textwrap

from parsers.csv_parser import CSVParser
from parsers.enhanced_transaction import Transaction  # Import enhanced model
from calculators.portfolio import Portfolio
from calculators.metrics import xirr, calculate_absolute_return
from services.market_data import fetch_prices, fetch_historical_prices
from services.corporate_actions import CorporateActionService
from services.fx_rates import FXRateService
from services.data_validator import DataValidator, ValidationIssue  # Data quality
from charts.visualizations import create_allocation_donut, create_performance_chart
from utils.logging_config import setup_logger
from utils.auth import check_authentication, show_logout_button
from services.market_cache import get_market_cache

logger = setup_logger(__name__)


@st.cache_data(show_spinner="🔄 Processing portfolio data...", ttl=3600)
def process_data_pipeline(file_content: str):
    """
    Process CSV content into enriched transactions with caching.
    Includes: Parse -> Splits -> FX -> Validation
    """
    try:
        # 1. Parse
        parser = CSVParser()
        transactions = parser.parse_csv(file_content)
        
        if not transactions:
            return None, [], 0, None
            
        # 1.5. ISIN Resolution
        # Convert ISINs to Tickers to ensure yfinance finds splits/prices
        from services.isin_resolver import ISINResolver
        
        tickers_to_check = {t.ticker for t in transactions if t.ticker}
        resolved_map = ISINResolver.resolve_batch(list(tickers_to_check))
        
        # Update transactions with resolved tickers
        resolved_count = 0
        for t in transactions:
            if t.ticker in resolved_map and resolved_map[t.ticker] != t.ticker:
                # Log only distinct changes to avoid massive spam
                # logger.debug(f"Mapping {t.ticker} -> {resolved_map[t.ticker]}")
                t.ticker = resolved_map[t.ticker]
                resolved_count += 1
                
        if resolved_count > 0:
            logger.info(f"Resolved ISINs to Tickers for {resolved_count} transactions")
        
        # 2. Splits
        # Note: CorporateActionService should have internal caching if possible, 
        # but this function cache covers it for the same file.
        transactions, split_log = CorporateActionService.detect_and_apply_splits(
            transactions,
            fetch_splits=True
        )
        
        # 3. FX Rates
        fx_conversions = 0
        for trans in transactions:
            if trans.original_currency != 'EUR':
                # Fetch historical FX rate for this transaction date
                historical_rate = FXRateService.get_rate(
                    trans.original_currency,
                    'EUR',
                    trans.date.date()
                )
                
                # Update FX rate if we got a historical one
                if historical_rate != trans.fx_rate:
                    trans.fx_rate = historical_rate
                    fx_conversions += 1
        
        # 4. Validation
        validator = DataValidator()
        validation_issues = validator.validate_all(transactions)
        val_summary = validator.get_summary()
        
        return transactions, split_log, fx_conversions, (validation_issues, val_summary)
        
    except Exception as e:
        logger.error(f"Pipeline processing error: {e}", exc_info=True)
        raise e


def parse_csv_only(file_content: str):
    """
    Parse CSV without enrichment (no API calls for splits/FX).
    Fast path for viewing cached data.
    
    Returns:
        (transactions, validation_data) or (None, None)
    """
    try:
        parser = CSVParser()
        transactions = parser.parse_csv(file_content)
        
        if not transactions:
            return None, None
        
        # Light validation only
        validator = DataValidator()
        validation_issues = validator.validate_all(transactions)
        val_summary = validator.get_summary()
        
        return transactions, (validation_issues, val_summary)
        
    except Exception as e:
        logger.error(f"CSV parsing error: {e}", exc_info=True)
        raise e




# Page configuration
st.set_page_config(
    page_title="Portfolio Viewer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - Cyber-Fintech Professional
st.markdown("""
<style>
    /* Import Professional Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    /* Design Tokens - Deep Space / FinTech */
    :root {
        --bg-color: #0b0e11;        /* Ultra dark slate */
        --sidebar-bg: #15191e;      /* Distinct sidebar */
        --card-bg: #1e2329;         /* Lighter card */
        --card-border: #2b313a;     /* Subtle border */
        --text-primary: #e6e6e6;
        --text-secondary: #8b949e;
        --accent-primary: #3b82f6;  /* Professional Blue */
        --accent-glow: rgba(59, 130, 246, 0.4);
        --accent-secondary: #6366f1; /* Indigo */
        --glass-bg: rgba(30, 35, 41, 0.7);
    }
    
    /* Global App Styling with Radial Gradient */
    .stApp {
        background-color: var(--bg-color);
        background-image: radial-gradient(circle at 50% 0%, #1f2937 0%, #0b0e11 75%);
        color: var(--text-primary);
        font-family: 'Inter', sans-serif;
    }
    
    /* Cyber-Tech Headers */
    /* Cyber-Tech Headers */
    /* Cyber-Tech Headers */
    .main-header {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem;
        font-weight: 600;
        color: var(--text-primary);
        letter-spacing: -0.02em;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
    }
    
    .sub-header {
        font-family: 'Inter', sans-serif;
        font-size: 0.8rem;
        font-weight: 600;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.15em;
        margin-bottom: 2rem;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    /* Removed the blue square decoration */

    /* Section Headers */
    h3 {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: var(--text-primary) !important;
        border-left: 4px solid var(--accent-primary);
        padding-left: 50px; /* Fixed: Greatly increased separation */
        margin-top: 2rem !important;
        margin-bottom: 1.5rem !important;
        background: linear-gradient(90deg, rgba(59, 130, 246, 0.1) 0%, transparent 100%);
        padding-top: 8px;
        padding-bottom: 8px;
    }
    
    /* CUSTOM CYBER METRIC CARD CSS */
    .cyber-metric-container {
        display: flex;
        flex-direction: column;
        background-color: #1e2329; /* card-bg */
        border: 1px solid #2b313a; /* card-border */
        border-top: 2px solid #2b313a;
        border-left: 3px solid #3b82f6; /* accent-primary */
        border-radius: 4px;
        padding: 12px 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        position: relative;
        overflow: hidden;
        margin-bottom: 1px;
        height: 100%;
        min-height: 85px;
        justify-content: center;
    }
    
    .cyber-metric-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(45deg, transparent 48%, rgba(59, 130, 246, 0.03) 50%, transparent 52%);
        background-size: 200% 200%;
        pointer-events: none;
    }

    .metric-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 500;
        color: #8b949e; /* text-secondary */
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 4px;
    }
    
    .metric-value-row {
        display: flex;
        align-items: baseline;
        gap: 8px;
    }
    
    .metric-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.4rem;
        font-weight: 700;
        color: #e6e6e6; /* text-primary */
        line-height: 1.1;
    }
    
    .metric-delta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        display: inline-flex;
        align-items: center;
        transform: translateY(-2px);
    }
    
    .delta-pos {
        color: #10b981;
        background-color: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.2);
    }
    
    .delta-neg {
        color: #ef4444;
        background-color: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    .delta-neu {
        color: #9CA3AF;
        background-color: rgba(156, 163, 175, 0.1);
        border: 1px solid rgba(156, 163, 175, 0.2);
    }
    
    /* Section Separation Line */
    hr {
        margin-top: 2rem;
        margin-bottom: 2rem;
        border: 0;
        border-top: 1px solid #2b313a;
    }
    
    /* NEW KPI DASHBOARD STYLES */
    .kpi-board {
        background-color: rgba(22, 27, 34, 0.5); 
        backdrop-filter: blur(10px);
        border: 1px solid var(--card-border);
        border-radius: 4px;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05); /* Subtle shadow */
        margin-bottom: 1rem; /* Standardized Gap */
    }
    
    .kpi-header {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 1.5rem;
        padding-left: 0;
    }
    
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(6, 1fr);
        gap: 0; /* Seamless look */
        /* border-top: 1px solid #2b313a; Optional separator from header */
    }
    
    .kpi-item {
        padding: 1rem;
        border-right: 1px solid rgba(255,255,255,0.05); /* Subtle separator */
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-height: 100px;
        transition: background 0.2s;
    }
    
    .kpi-item:last-child {
        border-right: none;
    }
    
    .kpi-item:hover {
        background-color: rgba(255,255,255,0.01);
    }
    
    .kpi-label {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem;
        font-weight: 500;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
    }
    
    .kpi-value-row {
        display: flex;
        align-items: baseline;
        gap: 8px;
    }
    
    .kpi-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.8rem; /* Larger, more impactful */
        font-weight: 700;
        color: var(--text-primary);
        line-height: 1;
    }
    
    /* Make Abs Gain (2nd item) stand out if needed, or all equal */

    
    /* Sidebar Headers */
    /* Sidebar Styling - Compact & Professional */
    [data-testid="stSidebar"] {
        background-color: #0d1117 !important;
        border-right: 1px solid var(--card-border);
    }
    
    [data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] div, [data-testid="stSidebar"] label {
        font-size: 0.85rem !important;
    }
    
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        font-family: 'JetBrains Mono', monospace !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stSidebar"] h3 {
        font-size: 0.8rem !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-top: 1.5rem !important;
        margin-bottom: 0.75rem !important;
        padding-left: 0 !important;
        border-left: none !important;
        color: var(--text-secondary) !important;
    }
    
    /* File Uploader in Sidebar */
    [data-testid="stFileUploader"] {
        padding: 0.5rem;
    }
    [data-testid="stFileUploader"] small {
        font-size: 0.75rem !important;
    }
    
    /* Expander Styling */
    .streamlit-expanderHeader {
        background-color: var(--card-bg) !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--card-border) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        border-radius: 4px;
        padding-left: 1rem !important;
    }
    
    .streamlit-expanderHeader p {
         font-family: 'JetBrains Mono', monospace !important;
         font-weight: 600 !important;
         font-size: 0.9rem !important;
    }
    
    [data-testid="stExpander"] {
        background-color: transparent !important;
        border: none !important;
        margin-bottom: 1rem;
        padding-top: 0 !important;
    }
    
    /* Expander Content Adjustment */
    [data-testid="stExpanderDetails"] > div {
        padding-bottom: 0.5rem !important; /* Reduce bottom padding */
        padding-top: 0.5rem !important;
    }

    /* Input Fields & Selectboxes */
    .stSelectbox label {
        font-size: 0.75rem !important;
        color: var(--text-secondary) !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.25rem !important;
    }
    
    .stSelectbox > div > div {
        background-color: var(--card-bg) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem !important;
        min-height: 38px;
    }
    
    /* Buttons usually */
    .stButton>button {
        background-color: var(--card-bg);
        color: var(--accent-primary);
        border: 1px solid var(--card-border);
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        transition: all 0.2s;
        padding: 0.6rem 1rem;
    }
    
    .stButton>button:hover {
        background: rgba(59, 130, 246, 0.1);
        border-color: var(--accent-primary);
        color: #fff;
        box-shadow: 0 0 15px rgba(59, 130, 246, 0.3);
    }
    
    /* Toggle Switch Styling */
    .stToggle {
        font-family: 'Inter', sans-serif;
    }
    
    /* Tables/Dataframes - Tile Style */
    .dataframe {
        background-color: var(--card-bg) !important;
        border: none !important;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .stDataFrame {
        border: none !important;
        background-color: transparent !important;
        box-shadow: none !important;
    }
    
    th {
        background-color: #11151a !important;
        color: var(--accent-primary) !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }
    
    td {
        color: var(--text-primary) !important;
        font-size: 0.8rem;
    }
    
    /* Chart Containers */
    /* Chart Containers */
    [data-testid="stPlotlyChart"] {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    

    
    /* Container Borders (st.container(border=True)) */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid var(--card-border) !important;
        background-color: var(--card-bg) !important;
        border-radius: 4px !important;
        padding: 1.5rem !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
        margin-bottom: 1rem !important; /* Standardized Gap */
    }
    
    /* Clean Card Titles (No Emoji/Blue Bar) */
    .card-title {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.1rem;
        font-weight: 600;
        color: var(--text-primary);
        margin-bottom: 1.5rem;
        /* No border, no extra decoration */
    }
    
</style>
""", unsafe_allow_html=True)


def render_kpi_dashboard(metrics):
    """
    Render the entire KPI dashboard as a single HTML block using CSS Grid.
    metrics: List of dicts with 'label', 'value', 'delta' (opt), 'delta_color' (opt)
    """
    items_html = ""
    for m in metrics:
        delta_html = ""
        if m.get('delta'):
            color_class = f"delta-{m.get('delta_color', 'neu')}"
            delta_html = f'<div class="metric-delta {color_class}">{m["delta"]}</div>'
            
        # Strictly no indentation in the f-string to prevent markdown code block
        items_html += f'<div class="kpi-item"><div class="kpi-label">{m["label"]}</div>'
        items_html += f'<div class="kpi-value-row"><div class="kpi-value">{m["value"]}</div>{delta_html}</div></div>'
        
    # Flatten string to avoid Markdown code block interpretation
    html = '<div class="kpi-board">'
    html += '<div class="kpi-header">Key Performance Indicators</div>'
    html += '<div class="kpi-grid">'
    html += items_html
    html += '</div></div>'
    
    return html

def main():
    """Main application entry point."""
    
    # Authentication check
    if not check_authentication():
        st.stop()
    
    show_logout_button()
    
    # Header - Cyber Tech
    st.markdown('<div class="main-header">PORTFOLIO DASHBOARD</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Financial Analytics & Performance Tracking</div>', unsafe_allow_html=True)
    
    # ==========================================
    # SIDEBAR: COMPACT & CLEAN
    # ==========================================
    with st.sidebar:
        st.markdown("### Data Source")
        
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
            st.caption(f"Cached: {cache_filename}")
            st.caption(f"Time: {uploaded_at.strftime('%m-%d %H:%M')}")
        
        if file_content is None:
            st.info("Awaiting Data Import")
            return

        # Session State Init
        if 'enrichment_done' not in st.session_state:
            st.session_state.enrichment_done = False
        if 'last_processed_content' not in st.session_state:
            st.session_state.last_processed_content = None
        
        # New File Reset Logic
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

        st.markdown("### Operations")
        
        # Action Buttons - Clean Text
        col_act1, col_act2 = st.columns(2)
        
        with col_act1:
            if st.button("REFRESH", use_container_width=True):
                st.session_state.enrichment_done = False
                st.rerun()
                
        with col_act2:
             if st.button("CLEAR", use_container_width=True):
                cache.clear_cache()
                st.rerun()

        st.markdown("---")
        
        # Privacy Mode Toggle
        if 'privacy_mode' not in st.session_state:
            st.session_state.privacy_mode = False
            
        privacy_mode = st.toggle("Privacy Mode", value=st.session_state.privacy_mode, help="Hide sensitive financial values")
        if privacy_mode != st.session_state.privacy_mode:
            st.session_state.privacy_mode = privacy_mode
            st.rerun()

    # ==========================================
    # MAIN DASHBOARD CONTENT
    # ==========================================
    
    # Process Data
    transactions = []
    
    # helper for privacy masking
    def mask_currency(val, is_private):
        return "••••••" if is_private else f"€{val:,.0f}"

    def mask_currency_precise(val, is_private):
        return "••••••" if is_private else f"€{val:,.2f}"

    if 'prices_updated' not in st.session_state:
        st.session_state.prices_updated = False

    # Determine if enrichment is requested or already done
    enrich_req = False # No longer a button, but can be triggered by REFRESH or initial load
    if not st.session_state.enrichment_done: # If not done, try to enrich
        enrich_req = True
    
    # Determine if prices update is requested
    price_req = st.session_state.prices_updated # This is now set by the REFRESH button or previous state

    try:
        if enrich_req or st.session_state.enrichment_done:
            transactions, split_log, fx_conversions, validation_data = process_data_pipeline(file_content)
            st.session_state.enrichment_done = True
        else:
            transactions, validation_data = parse_csv_only(file_content)
            split_log = []
            fx_conversions = 0
        
        if not transactions:
            st.error("No valid transactions found.")
            return

    except Exception as e:
        st.error(f"Processing Error: {str(e)}")
        return

    # Build Portfolio
    try:
        portfolio = Portfolio(transactions)
        tickers = portfolio.get_unique_tickers()
    except Exception as e:
        st.error(f"Portfolio Error: {str(e)}")
        return

    # Price Fetching
    if st.session_state.prices_updated:
        with st.spinner("Syncing market data..."):
            prices = fetch_prices(tickers)
        st.session_state.prices_updated = False # Reset after fetching
    else:
        prices = cache.get_prices_batch(tickers, datetime.now().date())

    # ==========================================
    # SIDEBAR STATUS GRID
    # ==========================================
    with st.sidebar:
        st.markdown("### System Status")
        
        # 2x2 Grid using columns
        row1_1, row1_2 = st.columns(2)
        row1_1.metric("TX Count", len(transactions))
        row1_2.metric("Assets", len(tickers))
        
        row2_1, row2_2 = st.columns(2)
        status_txt = "Active" if st.session_state.enrichment_done else "Pending"
        row2_1.metric("Enrichment", status_txt)
        
        live_prices_count = sum(1 for p in prices.values() if p is not None)
        row2_2.metric("Market Data", f"{live_prices_count}/{len(tickers)}")

        # Validation Warnings
        if validation_data:
             _, val_summary = validation_data
             if val_summary and (val_summary['ERROR'] > 0 or val_summary['WARNING'] > 0):
                 st.warning(f"Data Issues: {val_summary['ERROR']} Errors, {val_summary['WARNING']} Warnings")

    
    # Calculate metrics
    with st.spinner("🧮 calculating performance metrics..."):
        try:
            current_value = portfolio.calculate_total_value(prices)
            
            # XIRR calculation
            dates, amounts = portfolio.get_cash_flows_for_xirr(current_value)
            xirr_value = xirr(dates, amounts)
            
            # Absolute return
            abs_return, return_pct = calculate_absolute_return(
                portfolio.total_invested,
                portfolio.total_withdrawn,
                current_value
            )
            
        except Exception as e:
            st.error(f"❌ Failed to calculate metrics: {str(e)}")
            logger.error(f"Metrics calculation error: {e}", exc_info=True)
            return
    
    # Calculate explicit metrics (Restored)
    holdings_cost_basis = sum(pos.cost_basis for pos in portfolio.holdings.values())
    unrealized_gain = current_value - portfolio.cash_balance - holdings_cost_basis
    
    # Absolute Gain = Realized + Dividends + Interest + Unrealized - Fees
    total_absolute_gain = (portfolio.realized_gains + 
                          portfolio.total_dividends + 
                          portfolio.total_interest + 
                          unrealized_gain - 
                          portfolio.total_fees)
    
    # Calculate return % based on Cost Basis
    total_return_pct = (total_absolute_gain / holdings_cost_basis * 100) if holdings_cost_basis > 0 else 0
    gain_color = "pos" if total_absolute_gain >= 0 else "neg"
    gain_txt = f"+{total_return_pct:.1f}%" if total_absolute_gain >= 0 else f"{total_return_pct:.1f}%"

    # Prepare KPI Data with Privacy Masking
    kpi_data = [
        {"label": "Net Worth", "value": mask_currency(current_value, st.session_state.privacy_mode)},
        {"label": "Abs Gain", "value": mask_currency(total_absolute_gain, st.session_state.privacy_mode), "delta": gain_txt, "delta_color": gain_color},
        {"label": "XIRR", "value": f"{xirr_value * 100:.1f}%" if xirr_value is not None else "N/A", "delta": None, "delta_color": "pos" if xirr_value and xirr_value > 0 else "neu"},
        {"label": "Deposits", "value": mask_currency(portfolio.invested_capital, st.session_state.privacy_mode)},
        {"label": "Cost Basis", "value": mask_currency(holdings_cost_basis, st.session_state.privacy_mode)},
        {"label": "Fees", "value": mask_currency(portfolio.total_fees, st.session_state.privacy_mode)}
    ]

    # Optimized Layout: Single Container Tile
    st.markdown(render_kpi_dashboard(kpi_data), unsafe_allow_html=True)
    
    # st.divider() # Removed separator line
    
    # ==================== FETCH ALL HISTORICAL DATA ONCE ====================
    # This runs once and is cached - timeframe changes only filter the data
    # ONLY if transactions have been enriched (to avoid split API calls)
    
    if st.session_state.enrichment_done and transactions:
        # Determine the full date range needed
        earliest_transaction = min(t.date for t in transactions)
        latest_date = datetime.now()
        
        # Get all unique tickers
        all_tickers = set(t.ticker for t in transactions if t.ticker)
        
        # Fetch ALL historical prices once (cached by Streamlit)
        price_history = cache.get_historical_prices(all_tickers, earliest_transaction, latest_date)
        
        # Calculate daily portfolio values using the history
        dates, net_deposits, portfolio_values, cost_basis_values = portfolio.calculate_performance_history_optimized(
            price_history, earliest_transaction, latest_date
        )
    else:
        dates, net_deposits, portfolio_values, cost_basis_values = [], [], [], []

    # ==================== DASHBOARD CHARTS ====================
    
    # ==================== DASHBOARD CHARTS ====================
    # Container tile for charts
    with st.container(border=True):
        # Layout: Chart + Allocation (2 Columns)
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # 1. Get Timeframe from Session State (default to 'All')
            current_tf = st.session_state.get("performance_timeframe", "All")

            # 2. Filter Logic based on Timeframe
            if dates and current_tf != "All":
                days_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
                cutoff_date = (datetime.now() - timedelta(days=days_map.get(current_tf, 365))).date()
                
                # Filter lists
                filtered_indices = [i for i, d in enumerate(dates) if datetime.strptime(d[:10], '%Y-%m-%d').date() >= cutoff_date]
                if filtered_indices:
                    start_idx = filtered_indices[0]
                    d_dates = dates[start_idx:]
                    d_deposits = net_deposits[start_idx:]
                    d_values = portfolio_values[start_idx:]
                    if cost_basis_values:
                        d_basis = cost_basis_values[start_idx:]
                    else:
                        d_basis = None
                else:
                    d_dates, d_deposits, d_values, d_basis = [], [], [], []
            else:
                 d_dates, d_deposits, d_values, d_basis = dates, net_deposits, portfolio_values, cost_basis_values

            # 3. Render Chart FIRST (aligned with top of Allocation chart)
            chart_fig = create_performance_chart(
                d_dates, d_deposits, d_values, d_basis, 
                title="Performance History",
                privacy_mode=st.session_state.privacy_mode
            )
            st.plotly_chart(chart_fig, width='stretch')
            
            # 4. Render Timeframe Selector BELOW Chart
            selected_tf = st.selectbox(
                "Timeframe",
                options=["1M", "3M", "6M", "1Y", "All"],
                index=4, 
                key="performance_timeframe",
                label_visibility="visible" # Label visible per request
            )
            
            # Force rerun if changed to update chart immediately
            if selected_tf != current_tf:
                st.rerun()

        with col2:
            holdings_df = pd.DataFrame([
                {
                    'Ticker': h.ticker, 
                    'Name': h.name, 
                    'Market Value (EUR)': h.market_value, 
                    'Quantity': h.shares
                } 
                for h in portfolio.holdings.values() 
                if h.market_value > 0
            ])
            
            donut_fig = create_allocation_donut(
                holdings_df, 
                title="Portfolio Allocation",
                privacy_mode=st.session_state.privacy_mode
            )
            st.plotly_chart(donut_fig, width='stretch')
    
    # Holdings table
    with st.container(border=True):
        st.markdown('<div class="card-title">Current Holdings</div>', unsafe_allow_html=True)
        
        # Add filter controls
        filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 6])
        
        with filter_col1:
            asset_filter = st.selectbox(
                "Filter by Type",
                options=["All", "Assets Only", "Cash Only"],
                index=0,
                key="asset_type_filter"
            )
        
        with filter_col2:
            st.empty() # Placeholder
        
        try:
            holdings_df = portfolio.get_holdings_summary(prices)
            if not holdings_df.empty:
                # Apply filtering
                filtered_df = holdings_df.copy()
                
                if asset_filter == "Assets Only":
                    filtered_df = filtered_df[~filtered_df['Asset Type'].isin(['Cash', 'Unknown'])]
                elif asset_filter == "Cash Only":
                    filtered_df = filtered_df[filtered_df['Asset Type'] == 'Cash']
                
                if not filtered_df.empty:
                    # Format for display
                    holdings_display = filtered_df.copy()
                    holdings_display['Shares'] = holdings_display['Shares'].apply(lambda x: f"{x:.4f}")
                    holdings_display['Avg Cost (EUR)'] = holdings_display['Avg Cost (EUR)'].apply(lambda x: mask_currency_precise(x, st.session_state.privacy_mode))
                    holdings_display['Current Price (EUR)'] = holdings_display['Current Price (EUR)'].apply(lambda x: f"€{x:.2f}") # Unit prices usually visible? Or hide too? Hiding for consistency if user wants privacy.
                    # Actually, usually unit prices are fine, but balances are sensitive. User said "except unit prices".
                    # "removes the actual Euro values (except unit prices)" -> So KEEP Current Price visible.
                    
                    holdings_display['Market Value (EUR)'] = holdings_display['Market Value (EUR)'].apply(lambda x: mask_currency_precise(x, st.session_state.privacy_mode))
                    holdings_display['Gain/Loss (EUR)'] = holdings_display['Gain/Loss (EUR)'].apply(lambda x: mask_currency_precise(x, st.session_state.privacy_mode))
                    holdings_display['Gain %'] = holdings_display['Gain %'].apply(lambda x: f"{x:.2f}%")
                    
                    st.dataframe(
                        holdings_display,
                        width='stretch',
                        hide_index=True
                    )
                    
                    # Show filtered count
                    if asset_filter != "All":
                        st.caption(f"Showing {len(filtered_df)} of {len(holdings_df)} holdings")
                else:
                    st.info(f"No holdings match the filter: {asset_filter}")
            else:
                st.info("No current holdings")
        except Exception as e:
            st.error(f"Failed to display holdings: {e}")
            logger.error(f"Holdings display error: {e}", exc_info=True)
    
    # Additional info
    # Additional info
    # Reverted to Expander per user request
    with st.expander("Detailed Metrics"):
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        
        with summary_col1:
            st.metric("Cash Balance", mask_currency_precise(portfolio.cash_balance, st.session_state.privacy_mode))
            st.metric("Total Fees", mask_currency_precise(portfolio.total_fees, st.session_state.privacy_mode))
            st.metric("Total Interest", mask_currency_precise(portfolio.total_interest, st.session_state.privacy_mode))
        
        with summary_col2:
            st.metric("Realized Gains", mask_currency_precise(portfolio.realized_gains, st.session_state.privacy_mode))
            st.metric("Total Dividends", mask_currency_precise(portfolio.total_dividends, st.session_state.privacy_mode))

        with summary_col3:
            st.metric("Number of Holdings", len(portfolio.holdings))
            st.metric("Number of Transactions", len(transactions))
    
    # Transaction History
    # st.divider()
    
    with st.container(border=True):
        st.markdown('<div class="card-title">Transaction History</div>', unsafe_allow_html=True)
        
        try:
            # Create transaction history DataFrame
            trans_data = []
            for trans in sorted(transactions, key=lambda t: t.date, reverse=True):
                trans_data.append({
                    'Date': trans.date.strftime('%Y-%m-%d'),
                    'Type': trans.type.value,
                    'Ticker': trans.ticker or '-',
                    'Name': trans.name or '-',
                    'Asset Type': trans.asset_type.value if hasattr(trans, 'asset_type') else 'Unknown',
                    'Shares': float(trans.shares) if trans.shares != 0 else 0.0,  # Keep numeric for Arrow
                    'Price': f"€{float(trans.price):.2f}" if trans.price != 0 else '-',
                    'Fees': mask_currency_precise(float(trans.fees), st.session_state.privacy_mode) if trans.fees != 0 else '-',
                    'Total': mask_currency_precise(float(trans.total), st.session_state.privacy_mode),
                    'Currency': trans.original_currency,
                    'FX Rate': f"{float(trans.fx_rate):.4f}" if trans.fx_rate != 1 else '-',
                    'Broker': trans.broker or '-',
                })
            
            trans_df = pd.DataFrame(trans_data)
            
            if not trans_df.empty:
                # Add filters
                col_filter1, col_filter2, col_filter3 = st.columns(3)
                
                with col_filter1:
                    trans_types = ['All'] + sorted(trans_df['Type'].unique().tolist())
                    selected_type = st.selectbox("Filter by Type", trans_types)
                
                with col_filter2:
                    tickers = ['All'] + sorted([t for t in trans_df['Ticker'].unique() if t != '-'])
                    selected_ticker = st.selectbox("Filter by Ticker", tickers)
                
                with col_filter3:
                    # Enhanced filter options: Default to Assets Only (hide cash/no-ticker)
                    unique_asset_types = sorted(trans_df['Asset Type'].unique().tolist())
                    filter_options = ["Assets Only", "All"] + unique_asset_types
                    selected_asset_filter = st.selectbox("Filter by Asset Type", filter_options, index=0)
                
                # Apply filters
                filtered_df = trans_df.copy()
                if selected_type != 'All':
                    filtered_df = filtered_df[filtered_df['Type'] == selected_type]
                if selected_ticker != 'All':
                    filtered_df = filtered_df[filtered_df['Ticker'] == selected_ticker]
                
                # Apply Asset View Filter
                if selected_asset_filter == 'Assets Only':
                    # Filter out transactions with no ticker (Cash)
                    filtered_df = filtered_df[filtered_df['Ticker'] != '-']
                elif selected_asset_filter == 'All':
                    pass
                else:
                    # Specific asset type filter
                    filtered_df = filtered_df[filtered_df['Asset Type'] == selected_asset_filter]
                
                st.dataframe(
                    filtered_df,
                    width='stretch',
                    hide_index=True
                )
                
                st.caption(f"Showing {len(filtered_df)} of {len(trans_df)} transactions")
            else:
                st.info("No transactions to display")
                
        except Exception as e:
            st.error(f"Failed to display transaction history: {e}")
            logger.error(f"Transaction history error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
