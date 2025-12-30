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
    .main-header {
        font-family: 'JetBrains Mono', monospace;
        font-size: 2.5rem;
        font-weight: 700;
        letter-spacing: -0.05em;
        background: linear-gradient(90deg, #60A5FA 0%, #A78BFA 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        text-shadow: 0 0 30px rgba(59, 130, 246, 0.2);
    }
    
    .sub-header {
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        color: var(--text-secondary);
        font-weight: 400;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 2.5rem;
        display: flex;
        align-items: center;
        gap: 0.8rem;
    }
    
    .sub-header::before {
        content: '';
        display: block;
        width: 6px;
        height: 6px;
        background-color: var(--accent-primary);
        box-shadow: 0 0 8px var(--accent-primary);
    }

    /* Section Headers */
    h3 {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        color: var(--text-primary) !important;
        border-left: 4px solid var(--accent-primary);
        padding-left: 1.5rem; /* Increased Spacing */
        margin-top: 2rem !important;
        margin-bottom: 1.5rem !important;
        background: linear-gradient(90deg, rgba(59, 130, 246, 0.1) 0%, transparent 100%);
        padding-top: 5px;
        padding-bottom: 5px;
    }
    
    /* Dashboard Tiles (Metrics) */
    [data-testid="stMetric"] {
        background-color: var(--card-bg);
        border: 1px solid var(--card-border);
        border-top: 2px solid var(--card-border);
        padding: 0.8rem;
        border-radius: 4px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden; /* For scanline effect */
    }
    
    /* Subtle Scanline/Glow Effect */
    [data-testid="stMetric"]::after {
        content: " ";
        display: block;
        position: absolute;
        top: 0;
        left: 0;
        bottom: 0;
        right: 0;
        background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.1) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.03), rgba(0, 255, 0, 0.01), rgba(0, 0, 255, 0.03));
        z-index: 1;
        background-size: 100% 2px, 3px 100%;
        pointer-events: none;
    }

    [data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        top: -1px;
        left: -1px;
        width: 10px;
        height: 10px;
        border-top: 2px solid var(--accent-primary);
        border-left: 2px solid var(--accent-primary);
        border-radius: 4px 0 0 0;
        z-index: 2;
    }
    
    [data-testid="stMetric"]:hover {
        border-color: var(--accent-primary);
        transform: translateY(-2px);
        box-shadow: 0 8px 30px rgba(59, 130, 246, 0.15);
    }
    
    /* KPI Value & Delta Side-by-Side */
    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 1.5rem !important;
        font-weight: 700;
        color: var(--text-primary) !important;
        display: inline-block !important; /* Force inline */
    }
    
    [data-testid="stMetricDelta"] {
        display: inline-block !important; /* Force inline */
        margin-left: 12px !important;
        vertical-align: bottom !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem !important;
        background-color: rgba(0,0,0,0.2) !important;
        padding: 2px 6px !important;
        border-radius: 4px !important;
        position: relative; 
        top: -4px; /* Adjust alignment */
    }
    
    [data-testid="stMetricLabel"] {
        font-family: 'Inter', sans-serif;
        font-size: 0.75rem !important;
        color: var(--text-secondary) !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 4px !important;
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: var(--sidebar-bg);
        border-right: 1px solid var(--card-border);
    }
    
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        color: var(--text-secondary);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.2em;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    
    /* Input Fields & Selectboxes */
    .stSelectbox > div > div {
        background-color: var(--card-bg) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
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
    
    /* Tables/Dataframes - Tile Style */
    .dataframe {
        background-color: var(--card-bg) !important;
        border: none !important;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .stDataFrame {
        border: 1px solid var(--card-border);
        border-radius: 4px;
        background-color: var(--card-bg);
        padding: 1rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        position: relative;
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
    [data-testid="stPlotlyChart"] {
        background-color: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 4px;
        padding: 1rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
    
    /* Alerts */
    .stAlert {
        background-color: rgba(59, 130, 246, 0.05);
        border: 1px solid rgba(59, 130, 246, 0.2);
        color: var(--text-primary);
        border-radius: 4px;
    }
    
</style>
""", unsafe_allow_html=True)


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
            enrich_req = st.button("Enrich Data", use_container_width=True, help="Update metadata, splits, and FX")
        
        with col_act2:
            price_req = st.button("Update Prices", use_container_width=True, help="Fetch latest market prices")
            if price_req:
                st.session_state.prices_updated = True

        st.divider()

    # ==========================================
    # DATA PROCESSING
    # ==========================================
    
    if 'prices_updated' not in st.session_state:
        st.session_state.prices_updated = False

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
    
    # Display KPIs
    st.markdown('<h3 class="section-header">Key Performance Indicators</h3>', unsafe_allow_html=True)
    
    # Calculate explicit metrics
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
    
    # Optimized Layout: Single Compact Row of 6 Columns
    kpi_cols = st.columns(6)
    
    with kpi_cols[0]:
        st.metric(
            label="Net Worth",
            value=f"€{current_value:,.0f}", # No decimals for compactness
            help="Current portfolio value"
        )
    
    with kpi_cols[1]:
        st.metric(
            label="Abs Gain",
            value=f"€{total_absolute_gain:,.0f}",
            delta=f"{total_return_pct:.1f}%"
        )
    
    with kpi_cols[2]:
        if xirr_value is not None:
            st.metric("XIRR", f"{xirr_value * 100:.1f}%")
        else:
            st.metric("XIRR", "N/A")

    with kpi_cols[3]:
        st.metric("Deposits", f"€{portfolio.invested_capital:,.0f}")

    with kpi_cols[4]:
        st.metric("Cost Basis", f"€{holdings_cost_basis:,.0f}")
        
    with kpi_cols[5]:
        st.metric("Fees", f"€{portfolio.total_fees:,.0f}")
    
    st.divider()
    
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
        with st.spinner("Loading historical price data (one-time)..."):
            all_hist_prices_df = fetch_historical_prices(
                list(all_tickers),
                earliest_transaction.date(),
                latest_date.date()
            )
    else:
        all_hist_prices_df = pd.DataFrame()
    
    # ========================================================================
    
    # Optimized Chart Layout: Performance (2/3) | Allocation (1/3)
    chart_col_main, chart_col_side = st.columns([2, 1])
    
    with chart_col_main:
        st.markdown('<h3 class="section-header">Performance History</h3>', unsafe_allow_html=True)
        
        # Timeframe selector (inline)
        timeframe = st.selectbox(
            "Timeframe",
            options=["1M", "3M", "6M", "1Y", "All"],
            index=4,
            key="performance_timeframe",
            label_visibility="collapsed"
        )
        
        # Check if we have chart data (only available after enrichment)
        if not st.session_state.enrichment_done:
            st.info("📊 **Performance chart requires transaction enrichment**\n\nClick '🔄 Update Transactions' in the sidebar to:\n- Fetch split history\n- Update FX rates\n- Enable performance analysis")
        else:
            try:
                # Calculate date range based on timeframe (for filtering only)
                end_date = datetime.now()
                if timeframe == "1M":
                    start_date = end_date - timedelta(days=30)
                    interval_days = 2
                elif timeframe == "3M":
                    start_date = end_date - timedelta(days=90)
                    interval_days = 3
                elif timeframe == "6M":
                    start_date = end_date - timedelta(days=180)
                    interval_days = 7
                elif timeframe == "1Y":
                    start_date = end_date - timedelta(days=365)
                    interval_days = 7
                else:  # All
                    if transactions:
                        start_date = min(t.date for t in transactions)
                        total_days = (end_date - start_date).days
                        interval_days = 14 if total_days > 730 else 7
                    else:
                        start_date = end_date - timedelta(days=365)
                        interval_days = 7
                
                if transactions and not all_hist_prices_df.empty:
                    # Filter the already-loaded historical data by date range
                    hist_prices_df = all_hist_prices_df.copy()
                    if not hist_prices_df.empty:
                        # Filter to selected timeframe
                        mask = (hist_prices_df.index >= pd.Timestamp(start_date)) & (hist_prices_df.index <= pd.Timestamp(end_date))
                        hist_prices_df = hist_prices_df[mask]
                    
                    # Calculate at regular intervals for higher resolution
                    dates_list = []
                    net_deposits_list = []
                    value_list = []
                    cost_basis_list = []
                    
                    current_date = start_date
                    
                    # Pre-calculate prices map for speed
                    # Convert DataFrame to dictionary of dictionaries: {date: {ticker: price}}
                    # timestamp -> {ticker: price}
                    price_lookup = {}
                    if not hist_prices_df.empty:
                        # Iterate once to build lookup (faster than .loc inside loop)
                        for timestamp, row in hist_prices_df.iterrows():
                            # Convert timestamp to date object for matching
                            d_key = timestamp.date()
                            price_lookup[d_key] = {
                                t: float(p) for t, p in row.items() if pd.notna(p)
                            }

                    # OPTIMIZATION: Incremental Portfolio Update
                    # Sort transactions by date once
                    sorted_valid_trans = sorted(
                        [t for t in transactions if t.date <= end_date], 
                        key=lambda t: t.date
                    )
                    
                    # Initialize empty portfolio runner
                    running_portfolio = Portfolio([])
                    
                    trans_idx = 0
                    num_trans = len(sorted_valid_trans)
                    
                    while current_date <= end_date:
                        # Process all transactions that happened up to (and including) current_date
                        # that haven't been processed yet
                        while trans_idx < num_trans and sorted_valid_trans[trans_idx].date.date() <= current_date.date():
                            running_portfolio.process_transaction(sorted_valid_trans[trans_idx])
                            trans_idx += 1
                        
                        if trans_idx > 0: # Only record if we have started portfolio history
                            # Get prices for this date
                            daily_prices = price_lookup.get(current_date.date(), {})
                            
                            # Calculate value
                            temp_value = running_portfolio.calculate_total_value(daily_prices)
                            temp_cost_basis = sum(pos.cost_basis for pos in running_portfolio.holdings.values())
                            
                            dates_list.append(current_date.strftime('%Y-%m-%d'))
                            net_deposits_list.append(float(running_portfolio.invested_capital))
                            value_list.append(float(temp_value))
                            cost_basis_list.append(float(temp_cost_basis))
                        
                        current_date += timedelta(days=interval_days)
                    
                    if dates_list:
                        fig_performance = create_performance_chart(
                            dates_list, 
                            net_deposits_list, 
                            value_list,
                            cost_basis_list
                        )
                        st.plotly_chart(fig_performance, use_container_width=True)
                        
                        # Show data point count
                        st.caption(f"Showing {len(dates_list)} data points over {timeframe}")
                    else:
                        st.info("Not enough historical data for selected timeframe")
                else:
                    st.info("No transactions available for chart")
                        
            except Exception as e:
                st.error(f"Failed to create performance chart: {e}")
                logger.error(f"Performance chart error: {e}", exc_info=True)
            
    with chart_col_side:
        st.markdown('<h3 class="section-header">Portfolio Allocation</h3>', unsafe_allow_html=True)
        try:
            holdings_df = portfolio.get_holdings_summary(prices)
            if not holdings_df.empty:
                fig_allocation = create_allocation_donut(holdings_df)
                st.plotly_chart(fig_allocation, use_container_width=True)
            else:
                st.info("No holdings to display")
        except Exception as e:
            st.error(f"Failed to create allocation chart: {e}")
            logger.error(f"Allocation chart error: {e}", exc_info=True)
    
    st.divider()
    
    # Holdings table
    st.markdown('<h3 class="section-header">Current Holdings</h3>', unsafe_allow_html=True)
    
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
        # Placeholder for future filters
        st.empty()
    
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
                holdings_display['Avg Cost (EUR)'] = holdings_display['Avg Cost (EUR)'].apply(lambda x: f"€{x:.2f}")
                holdings_display['Current Price (EUR)'] = holdings_display['Current Price (EUR)'].apply(lambda x: f"€{x:.2f}")
                holdings_display['Market Value (EUR)'] = holdings_display['Market Value (EUR)'].apply(lambda x: f"€{x:,.2f}")
                holdings_display['Gain/Loss (EUR)'] = holdings_display['Gain/Loss (EUR)'].apply(lambda x: f"€{x:,.2f}")
                holdings_display['Gain %'] = holdings_display['Gain %'].apply(lambda x: f"{x:.2f}%")
                
                st.dataframe(
                    holdings_display,
                    use_container_width=True,
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
    with st.expander("ℹ️ Detailed Metrics"):
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        
        with summary_col1:
            st.metric("Cash Balance", f"€{portfolio.cash_balance:,.2f}")
            st.metric("Total Fees", f"€{portfolio.total_fees:,.2f}")
            st.metric("Total Interest", f"€{portfolio.total_interest:,.2f}")
        
        with summary_col2:
            st.metric("Realized Gains", f"€{portfolio.realized_gains:,.2f}")
            st.metric("Total Dividends", f"€{portfolio.total_dividends:,.2f}")

        with summary_col3:
            st.metric("Number of Holdings", len(portfolio.holdings))
            st.metric("Number of Transactions", len(transactions))
    
    # Transaction History
    st.divider()
    st.subheader("📝 Transaction History")
    
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
                'Fees': f"€{float(trans.fees):.2f}" if trans.fees != 0 else '-',
                'Total': f"€{float(trans.total):,.2f}",
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
                use_container_width=True,
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
