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



# Page configuration
st.set_page_config(
    page_title="Portfolio Viewer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #6B7280;
        margin-bottom: 2rem;
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
    st.markdown('<div class="sub-header">Parqet-lite portfolio tracker with XIRR calculations</div>', unsafe_allow_html=True)
    
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
    elif 'use_cache' in st.session_state and st.session_state['use_cache']:
        file_content = st.session_state['cached_csv']
        filename = st.session_state['cached_filename']
        using_cache = True
        st.sidebar.success(f"✅ Using cached data: {filename}")
        
    if file_content is None:
        # No active data source - Show Welcome / Load Cache UI
        
        if cached_data:
            csv_content, cache_filename, uploaded_at = cached_data
            st.info(f"📦 Found cached portfolio data from {uploaded_at.strftime('%Y-%m-%d %H:%M')}")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                if st.button("📂 Load Cached Data", type="primary", use_container_width=True):
                    st.session_state['use_cache'] = True
                    st.session_state['cached_csv'] = csv_content
                    st.session_state['cached_filename'] = cache_filename
                    st.rerun()
            with col2:
                st.caption(f"Last file: {cache_filename}")
        else:
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
    # Process data pipeline (Cached)
    try:
        transactions, split_log, fx_conversions, validation_data = process_data_pipeline(file_content)
        
        if not transactions:
            st.error("No valid transactions found in CSV")
            return
            
        st.sidebar.success(f"✅ Parsed {len(transactions)} transactions")
        
        # Save to cache if this was a new upload and successful
        if uploaded_file is not None:
            cache.save_transactions_csv(file_content, filename)
            st.sidebar.info("💾 Saved to cache for next login")
        
        # Display Split info
        if split_log:
            st.sidebar.info(f"📊 Applied {len(split_log)} split adjustments")
            with st.sidebar.expander("Split Adjustments", expanded=False):
                for log_entry in split_log[:5]:
                    st.text(log_entry)
                if len(split_log) > 5:
                    st.text(f"... and {len(split_log) - 5} more")
        
        # Display FX info
        if fx_conversions > 0:
            st.sidebar.success(f"💱 Applied {fx_conversions} historical FX rates")
            
        # Display Validation info
        if validation_data:
            validation_issues, summary = validation_data
            if summary and summary['ERROR'] > 0:
                st.sidebar.error(f"❌ {summary['ERROR']} data errors found")
                with st.sidebar.expander("Data Quality Report", expanded=True):
                    for issue in validation_issues[:10]:
                        st.text(f"❌ {issue.message}")
            elif summary and summary['WARNING'] > 0:
                st.sidebar.warning(f"⚠️ {summary['WARNING']} warnings")
    
    except Exception as e:
        st.error(f"❌ Failed to process data: {str(e)}")
        # Don't return, let user retry or see stuck state
        return
    
    # Build portfolio
    with st.spinner("💼 Reconstructing portfolio state..."):
        try:
            portfolio = Portfolio(transactions)
            tickers = portfolio.get_unique_tickers()
            
            st.sidebar.info(f"📈 {len(tickers)} unique tickers")
            
        except Exception as e:
            st.error(f"❌ Failed to build portfolio: {str(e)}")
            logger.error(f"Portfolio reconstruction error: {e}", exc_info=True)
            return
    
    # Fetch market data
    with st.spinner("🌐 Fetching live market data..."):
        try:
            prices = fetch_prices(tickers)
            
            # Count successful/failed fetches
            success_count = sum(1 for p in prices.values() if p is not None)
            failed_tickers = [t for t, p in prices.items() if p is None]
            
            if failed_tickers:
                with st.sidebar:
                    with st.expander(f"⚠️ {len(failed_tickers)} tickers failed", expanded=False):
                        st.warning("Using last transaction price as fallback:")
                        for ticker in failed_tickers[:10]:  # Show max 10
                            st.text(f"• {ticker}")
                        if len(failed_tickers) > 10:
                            st.text(f"... and {len(failed_tickers) - 10} more")
            else:
                st.sidebar.success(f"✅ Fetched prices for all {success_count} tickers")
            
        except Exception as e:
            st.error(f"❌ Failed to fetch market data: {str(e)}")
            logger.error(f"Market data fetch error: {e}", exc_info=True)
            # Continue with empty prices dict
            prices = {}
    
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
    
    # Absolute Gain = Realized + Dividends + Interest + Unrealized
    # This method is robust against missing deposit history (unlike "Net Worth - Net Invested")
    total_absolute_gain = (portfolio.realized_gains + 
                          portfolio.total_dividends + 
                          portfolio.total_interest + 
                          unrealized_gain)
    
    # Calculate return % based on Cost Basis (more accurate reflection of performance than Net Deposits)
    total_return_pct = (total_absolute_gain / holdings_cost_basis * 100) if holdings_cost_basis > 0 else 0
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Net Worth",
            value=f"€{current_value:,.2f}",
            help="Current portfolio value (Holdings + Cash)"
        )
    
    with col2:
        st.metric(
            label="Net Deposits",
            value=f"€{portfolio.invested_capital:,.2f}",
            help="Total Cash Deposited - Total Cash Withdrawn"
        )

    with col3:
        st.metric(
            label="Cost Basis",
            value=f"€{holdings_cost_basis:,.2f}",
            help="Total cost of current holdings"
        )
    
    with col4:
        gain_color = "normal" if total_absolute_gain >= 0 else "inverse"
        st.metric(
            label="Absolute Gain",
            value=f"€{total_absolute_gain:,.2f}",
            delta=f"{total_return_pct:.2f}%",
            help="Realized + Dividends + Interest + (Market Value - Cost Basis)"
        )
    
    with col5:
        if xirr_value is not None:
            xirr_pct = xirr_value * 100
            st.metric(
                label="XIRR",
                value=f"{xirr_pct:.2f}%",
                help="Annualized money-weighted return"
            )
        else:
            st.metric(
                label="XIRR",
                value="N/A",
                help="Not enough data or invalid cash flow pattern"
            )
    
    st.divider()
    
    # Two-column layout for visualizations
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
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
    
    with col_right:
        st.subheader("📈 Performance History")
        
        # Timeframe selector
        timeframe_col1, timeframe_col2 = st.columns([3, 7])
        with timeframe_col1:
            timeframe = st.selectbox(
                "Timeframe",
                options=["1M", "3M", "6M", "1Y", "All"],
                index=3,  # Default to 1Y
                key="performance_timeframe"
            )
        
        try:
            # Calculate date range based on timeframe
            end_date = datetime.now()
            if timeframe == "1M":
                start_date = end_date - timedelta(days=30)
                interval_days = 2  # Every 2 days
            elif timeframe == "3M":
                start_date = end_date - timedelta(days=90)
                interval_days = 3  # Every 3 days
            elif timeframe == "6M":
                start_date = end_date - timedelta(days=180)
                interval_days = 7  # Weekly
            elif timeframe == "1Y":
                start_date = end_date - timedelta(days=365)
                interval_days = 7  # Weekly
            else:  # All
                # Use first transaction date
                if transactions:
                    start_date = min(t.date for t in transactions)
                    # Adjust interval based on total duration
                    total_days = (end_date - start_date).days
                    if total_days > 730:  # > 2 years
                        interval_days = 14  # Bi-weekly
                    else:
                        interval_days = 7  # Weekly
                else:
                    start_date = end_date - timedelta(days=365)
                    interval_days = 7
            
            # Filter transactions within date range
            hist_trans = [t for t in transactions if start_date.date() <= t.date.date() <= end_date.date()]
            
            if hist_trans or timeframe == "All":
                # Fetch historical prices for ALL involved tickers for correct valuation
                impacted_tickers = set(t.ticker for t in transactions if t.ticker)
                
                with st.spinner("📉 Loading historical price data..."):
                    hist_prices_df = fetch_historical_prices(
                        list(impacted_tickers),
                        start_date.date(),
                        end_date.date()
                    )
                
                # Calculate at regular intervals for higher resolution
                dates_list = []
                net_deposits_list = []
                value_list = []
                cost_basis_list = []
                
                current_date = start_date
                
                # Pre-calculate prices map for speed if possible, or just use df usage inside loop
                
                while current_date <= end_date:
                    # Get transactions up to this date
                    # OPTIMIZATION: Assuming transactions are sorted by date
                    trans_until = [t for t in transactions if t.date <= current_date]
                    
                    if trans_until:
                        temp_portfolio = Portfolio(trans_until) # This is effectively an accumulator/snapshot
                        
                        # CRITICAL FIX: Use prices AT current_date, not today's prices
                        # Build price map for this date
                        daily_prices = {}
                        date_key = pd.Timestamp(current_date.date())
                        
                        if not hist_prices_df.empty:
                            try:
                                # Get row for this date (nearest available previous date via ffill)
                                # Since we reindexed to daily and ffilled in fetch_historical_prices, .loc should work
                                # But let's use asof/nearest logic if index mismatch, though reindex handles it.
                                if date_key in hist_prices_df.index:
                                    row = hist_prices_df.loc[date_key]
                                    daily_prices = row.to_dict()
                                    # Convert to float/None
                                    final_prices = {}
                                    for t, p in daily_prices.items():
                                        if pd.notna(p):
                                            final_prices[t] = float(p)
                                        else:
                                            final_prices[t] = None
                                    daily_prices = final_prices
                            except Exception as price_err:
                                # Fallback or just empty
                                pass
                        
                        # Use daily prices for historical value
                        temp_value = temp_portfolio.calculate_total_value(daily_prices)
                        temp_cost_basis = sum(pos.cost_basis for pos in temp_portfolio.holdings.values())
                        
                        dates_list.append(current_date.strftime('%Y-%m-%d'))
                        net_deposits_list.append(float(temp_portfolio.invested_capital))
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
                st.info(f"No transactions in the selected timeframe ({timeframe})")
                
        except Exception as e:
            st.error(f"Failed to create performance chart: {e}")
            logger.error(f"Performance chart error: {e}", exc_info=True)
    
    st.divider()
    
    # Holdings table
    st.subheader("📋 Current Holdings")
    
    # Add filter controls (before fetching data, so they don't trigger refresh)
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
            # Apply filtering on the already-loaded data (no API/DB calls)
            filtered_df = holdings_df.copy()
            
            if asset_filter == "Assets Only":
                # Exclude cash-like assets
                filtered_df = filtered_df[~filtered_df['Asset Type'].isin(['Cash', 'Unknown'])]
            elif asset_filter == "Cash Only":
                # Only show cash
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
