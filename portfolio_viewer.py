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

# Custom CSS - Banking-Grade Professional UI
st.markdown("""
<style>
    /* Import Professional Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    /* Design Tokens */
    :root {
        --primary-blue: #2563EB;
        --primary-dark: #1E40AF;
        --success-green: #10B981;
        --gray-50: #F9FAFB;
        --gray-100: #F3F4F6;
        --gray-600: #4B5563;
        --gray-700: #374151;
        --gray-900: #111827;
    }
    
    /* Global Font */
    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    /* Main Header with Gradient */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, var(--primary-blue) 0%, var(--primary-dark) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin-bottom: 0.5rem;
        letter-spacing: -0.025em;
        animation: fadeInDown 0.6s ease-out;
    }
    
    .sub-header {
        font-size: 1.2rem;
        color: var(--gray-600);
        margin-bottom: 2rem;
        font-weight: 400;
        animation: fadeInUp 0.6s ease-out 0.2s both;
    }
    
    /* Professional Metric Cards */
    [data-testid="stMetric"] {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);
        border: 1px solid var(--gray-100);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    
    [data-testid="stMetric"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.02) 0%, rgba(30, 64, 175, 0.05) 100%);
        opacity: 0;
        transition: opacity 0.3s;
        pointer-events: none;
    }
    
    [data-testid="stMetric"]:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
        border-color: var(--primary-blue);
    }
    
    [data-testid="stMetric"]:hover::before {
        opacity: 1;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
        color: var(--gray-900);
        letter-spacing: -0.02em;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.875rem;
        font-weight: 600;
        color: var(--gray-600);
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Professional Button Styling */
    .stButton>button {
        background: linear-gradient(135deg, var(--primary-blue) 0%, var(--primary-dark) 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 12px rgba(37, 99, 235, 0.4);
    }
    
    /* Enhanced Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--gray-50) 0%, white 100%);
    }
    
    /* Dataframe Styling */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        border: 1px solid var(--gray-100);
    }
    
    .dataframe thead th {
        background: var(--gray-100);
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    
    .dataframe tbody tr:hover {
        background: var(--gray-50);
    }
    
    /* Plotly Chart Container */
    .js-plotly-plot {
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07);
        border: 1px solid var(--gray-100);
    }
    
    /* Animations */
    @keyframes fadeInDown {
        from {
            opacity: 0;
            transform: translateY(-20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* Responsive Design */
    @media (max-width: 768px) {
        .main-header {
            font-size: 2rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)


def main():
    """Main application entry point."""
    
    # Authentication check
    if not check_authentication():
        st.stop()  # Stop execution if not authenticated
    
    # Show logout button for authenticated users
    show_logout_button()
    
    # Header
    st.markdown('<div class="main-header">📊 Portfolio Viewer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Professional portfolio tracker with XIRR calculations</div>', unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.header("📁 Data Import")
        
        uploaded_file = st.file_uploader(
            "Upload Transaction CSV",
            type=['csv'],
            help="Upload your transaction history in CSV format (max 10MB)"
        )
        
        if uploaded_file is not None:
            # Check file size
            file_size = uploaded_file.size
            if file_size > 10 * 1024 * 1024:  # 10MB
                st.error("File size exceeds 10MB limit")
                return
            
            st.success(f"File uploaded: {uploaded_file.name} ({file_size / 1024:.1f} KB)")
        
        st.divider()
        st.caption("💡 Tip: Your CSV should contain columns like Date, Type, Ticker, Shares, Price, Fees")
    
    # Main content

    # Check for cached transactions
    cache = get_market_cache()
    cached_data = cache.get_last_transactions_csv()
    
    # Determine data source
    file_content = None
    filename = None
    using_cache = False

    if uploaded_file is not None:
        file_content = uploaded_file.getvalue().decode('utf-8')
        filename = uploaded_file.name
        # Save to cache for future auto-loading
        try:
            cache.save_transactions_csv(file_content, filename)
            logger.info(f"Saved CSV to cache: {filename}")
        except Exception as e:
            logger.error(f"Failed to save CSV to cache: {e}")
    elif cached_data:
        # Auto-load from cache
        csv_content, cache_filename, uploaded_at = cached_data
        file_content = csv_content
        filename = cache_filename
        using_cache = True
        # Sidebar notification (simplified)
        st.sidebar.info(f"📂 Auto-loaded: {cache_filename}\n{uploaded_at.strftime('%Y-%m-%d %H:%M')}")

    if file_content is None:
        # No upload AND no cache - Show Welcome
        st.info("👆 Upload a CSV file to get started")
        
        with st.expander("📋 Supported CSV Format"):
            st.markdown("""
            **Required Columns:**
            - `Date` (or datetime, datum)
            - `Type` (Buy, Sell, Dividend, TransferIn, TransferOut, Interest)
            
            **Optional Columns:**
            - `Ticker` (or symbol, ISIN, identifier)
            - `Shares` (or amount, quantity)
            - `Price` (or unit_price)
            - `Fees` (or fee, commission)
            - `Total` (net cash flow)
            - `Currency` (or originalcurrency)
            - `FXRate` (exchange rate to EUR)
            
            **Format Detection:**
            - Automatically detects delimiter (; or ,)
            - Handles German decimal format (comma as separator)
            - Fuzzy column name matching
            """)
        
        with st.expander("📊 Features"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
                **Performance Metrics:**
                - XIRR (money-weighted return)
                - Absolute return (€ and %)
                - Net worth calculation
                - Holdings summary
                """)
            with col2:
                st.markdown("""
                **Visualizations:**
                - Portfolio allocation donut chart
                - Performance history area chart
                - Interactive hover tooltips
                - Responsive design
                """)
        
        return
    
    # Initialize session state for manual update control
    if 'enrichment_done' not in st.session_state:
        st.session_state.enrichment_done = False
    if 'last_processed_content' not in st.session_state:
        st.session_state.last_processed_content = None
    
    # Check if we need to reset enrichment status (new file)
    if st.session_state.last_processed_content != file_content:
        st.session_state.enrichment_done = False
        st.session_state.last_processed_content = file_content
    
    # Manual Update Controls in Sidebar
    with st.sidebar:
        st.markdown("---")
        st.markdown("### ⚙️ Data Operations")
        
        # Button to enrich transactions (splits, FX, ISINs)
        enrich_button = st.button(
            "🔄 Update Transactions",
            help="Fetch splits, update FX rates, resolve ISINs (takes ~10 min)",
            use_container_width=True,
            type="secondary" if not st.session_state.enrichment_done else "primary"
        )
        
        if not st.session_state.enrichment_done:
            st.caption("⚠️ Transactions not enriched yet")
        else:
            st.caption("✅ Transactions enriched")
    
    # Process data based on enrichment state
    try:
        if enrich_button or st.session_state.enrichment_done:
            # Full pipeline with API calls
            transactions, split_log, fx_conversions, validation_data = process_data_pipeline(file_content)
            st.session_state.enrichment_done = True
            
            if not transactions:
                st.error("No valid transactions found in CSV")
                return
                
            # Status display
            with st.sidebar:
                st.markdown("---")
                st.markdown("### 🛠️ Data Status")
                
                status_lines = []
                status_lines.append(f"• **Parsed:** {len(transactions)} transactions")
                
                if split_log:
                    status_lines.append(f"• **Splits:** {len(split_log)} applied")
                
                if fx_conversions > 0:
                    status_lines.append(f"• **FX:** {fx_conversions} historical rates")
                
                for line in status_lines:
                    st.markdown(f"<small>{line}</small>", unsafe_allow_html=True)

                # Data Quality / Warnings
                if validation_data:
                    validation_issues, summary = validation_data
                    if summary and (summary['ERROR'] > 0 or summary['WARNING'] > 0):
                        with st.expander("🔍 Data Quality Details", expanded=False):
                            if summary['ERROR'] > 0:
                                st.markdown(f"**Errors:** {summary['ERROR']}")
                            if summary['WARNING'] > 0:
                                st.markdown(f"**Warnings:** {summary['WARNING']}")
                            for issue in validation_issues[:5]:
                                st.caption(f"• {issue.message}")
                
                if uploaded_file is not None:
                    st.caption("💾 Saved to local cache")
                st.markdown("---")
        else:
            # Fast path: parse only, no API calls
            transactions, validation_data = parse_csv_only(file_content)
            
            if not transactions:
                st.error("No valid transactions found in CSV")
                return
            
            # Minimal status
            with st.sidebar:
                st.markdown("---")
                st.markdown("### 🛠️ Data Status")
                st.markdown(f"<small>• **Parsed:** {len(transactions)} transactions</small>", unsafe_allow_html=True)
                st.markdown(f"<small>• **Mode:** View only (no enrichment)</small>", unsafe_allow_html=True)
                
                if uploaded_file is not None:
                    st.caption("💾 Saved to local cache")
                st.markdown("---")

    except Exception as e:
        st.error(f"❌ Failed to process data: {str(e)}")
        return

    
    # Build portfolio
    try:
        portfolio = Portfolio(transactions)
        tickers = portfolio.get_unique_tickers()
        
        with st.sidebar:
            st.markdown(f"<small>• **Universe:** {len(tickers)} unique tickers</small>", unsafe_allow_html=True)
            
    except Exception as e:
        st.error(f"❌ Failed to build portfolio: {str(e)}")
        logger.error(f"Portfolio reconstruction error: {e}", exc_info=True)
        return
    
    # Initialize session state for price updates
    if 'prices_updated' not in st.session_state:
        st.session_state.prices_updated = False
    
    # Manual Price Update Button in Sidebar
    with st.sidebar:
        update_prices_button = st.button(
            "💰 Update Prices",
            help="Fetch latest market prices from APIs (uses cache when possible)",
            use_container_width=True,
            type="secondary"
        )
        
        if update_prices_button:
            st.session_state.prices_updated = True
    
    # Fetch market data only if requested or already done
    if st.session_state.prices_updated or update_prices_button:
        with st.spinner("🌐 Fetching live market data..."):
            try:
                prices = fetch_prices(tickers)
                
                # Count successful/failed fetches
                success_count = sum(1 for p in prices.values() if p is not None)
                failed_tickers = [t for t, p in prices.items() if p is None]
                
                with st.sidebar:
                    if failed_tickers:
                         with st.expander(f"⚠️ {len(failed_tickers)} pricing issues", expanded=False):
                            for ticker in failed_tickers[:10]:
                                st.caption(f"• {ticker}: Fallback used")
                    else:
                        st.markdown(f"<small>• **Live Data:** {success_count}/{len(tickers)} active</small>", unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"❌ Failed to fetch market data: {str(e)}")
                prices = {}
    else:
        # Use cached prices only (fast path)
        cache = get_market_cache()
        prices = cache.get_prices_batch(tickers, datetime.now().date())
        
        # Count how many we have cached
        cached_count = sum(1 for p in prices.values() if p is not None)
        
        with st.sidebar:
            if cached_count > 0:
                st.markdown(f"<small>• **Cached Prices:** {cached_count}/{len(tickers)}</small>", unsafe_allow_html=True)
                st.caption("💡 Click 'Update Prices' to refresh")
            else:
                st.warning("⚠️ No cached prices - click 'Update Prices'")

    
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
    st.subheader("📊 Key Performance Indicators")
    
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
    
    # Optimized Layout for FHD: 3 Top Metrics + 3 Secondary
    m_col1, m_col2, m_col3 = st.columns(3)
    
    with m_col1:
        st.metric(
            label="Net Worth",
            value=f"€{current_value:,.2f}",
            help="Current portfolio value (Holdings + Cash)"
        )
    
    with m_col2:
        gain_color = "normal" if total_absolute_gain >= 0 else "inverse"
        st.metric(
            label="Absolute Gain",
            value=f"€{total_absolute_gain:,.2f}",
            delta=f"{total_return_pct:.2f}%",
            help="Realized + Dividends + Interest + (MV - Cost) - Fees"
        )
    
    with m_col3:
        if xirr_value is not None:
            xirr_pct = xirr_value * 100
            st.metric(
                label="XIRR",
                value=f"{xirr_pct:.2f}%",
                help="Annualized money-weighted return"
            )
        else:
            st.metric("XIRR", "N/A")
            
    # Secondary Metrics Row
    m_col4, m_col5, m_col6 = st.columns(3)
    with m_col4:
        st.metric("Net Deposits", f"€{portfolio.invested_capital:,.2f}")
    with m_col5:
        st.metric("Cost Basis", f"€{holdings_cost_basis:,.2f}")
    with m_col6:
        st.metric("Total Fees", f"€{portfolio.total_fees:,.2f}")
    
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
        with st.spinner("📉 Loading historical price data (one-time)..."):
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
        st.subheader("📈 Performance History")
        
        # Timeframe selector (inline)
        timeframe = st.selectbox(
            "Timeframe",
            options=["1M", "3M", "6M", "1Y", "All"],
            index=3,
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
        st.subheader("🥧 Portfolio Allocation")
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
    st.subheader("📋 Current Holdings")
    
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
                holdings_display['Avg Cost'] = holdings_display['Avg Cost'].apply(lambda x: f"€{x:.2f}")
                holdings_display['Current Price'] = holdings_display['Current Price'].apply(lambda x: f"€{x:.2f}")
                holdings_display['Market Value'] = holdings_display['Market Value'].apply(lambda x: f"€{x:,.2f}")
                holdings_display['Gain/Loss'] = holdings_display['Gain/Loss'].apply(lambda x: f"€{x:,.2f}")
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
                asset_types = ['All'] + sorted(trans_df['Asset Type'].unique().tolist())
                selected_asset_type = st.selectbox("Filter by Asset Type", asset_types)
            
            # Apply filters
            filtered_df = trans_df.copy()
            if selected_type != 'All':
                filtered_df = filtered_df[filtered_df['Type'] == selected_type]
            if selected_ticker != 'All':
                filtered_df = filtered_df[filtered_df['Ticker'] == selected_ticker]
            if selected_asset_type != 'All':
                filtered_df = filtered_df[filtered_df['Asset Type'] == selected_asset_type]
            
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
