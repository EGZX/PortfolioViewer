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
from services.market_data import fetch_prices
from services.corporate_actions import CorporateActionService
from services.fx_rates import FXRateService
from services.data_validator import DataValidator, ValidationIssue  # Data quality
from charts.visualizations import create_allocation_donut, create_performance_chart
from utils.logging_config import setup_logger
from utils.auth import check_authentication, show_logout_button

logger = setup_logger(__name__)


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
    if uploaded_file is None:
        # Welcome screen
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
    
    # Process file
    with st.spinner("📖 Parsing CSV..."):
        try:
            file_content = uploaded_file.getvalue().decode('utf-8')
            parser = CSVParser()
            transactions = parser.parse_csv(file_content)
            
            if not transactions:
                st.error("No valid transactions found in CSV")
                return
            
            st.sidebar.success(f"✅ Parsed {len(transactions)} transactions")
            
        except Exception as e:
            st.error(f"❌ Failed to parse CSV: {str(e)}")
            logger.error(f"CSV parsing error: {e}", exc_info=True)
            return
    
    # Apply stock split adjustments
    with st.spinner("🔄 Detecting and applying stock splits..."):
        try:
            adjusted_transactions, split_log = CorporateActionService.detect_and_apply_splits(
                transactions,
                fetch_splits=True
            )
            
            transactions = adjusted_transactions
            
            if split_log:
                st.sidebar.info(f"📊 Applied {len(split_log)} split adjustments")
                with st.sidebar.expander("Split Adjustments", expanded=False):
                    for log_entry in split_log[:5]:  # Show first 5
                        st.text(log_entry)
                    if len(split_log) > 5:
                        st.text(f"... and {len(split_log) - 5} more")
            else:
                st.sidebar.info("✓ No splits detected")
                
        except Exception as e:
            st.warning(f"⚠️ Could not fetch split data: {str(e)}")
            logger.error(f"Split detection error: {e}", exc_info=True)
            # Continue without split adjustments
    
    # Apply historical FX rates (convert to EUR at historical rates)
    with st.spinner("💱 Applying historical FX rates..."):
        try:
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
            
            if fx_conversions > 0:
                st.sidebar.success(f"💱 Applied {fx_conversions} historical FX rates")
            
        except Exception as e:
            st.warning(f"⚠️ Could not fetch historical FX rates: {str(e)}")
            logger.error(f"Historical FX error: {e}", exc_info=True)
            # Continue with default/current FX rates
    
    # Validate data quality
    with st.spinner("✓ Validating data quality..."):
        try:
            validator = DataValidator()
            validation_issues = validator.validate_all(transactions)
            summary = validator.get_summary()
            
            if validation_issues:
                # Display validation summary in sidebar
                if summary['ERROR'] > 0:
                    st.sidebar.error(f"❌ {summary['ERROR']} data errors found")
                if summary['WARNING'] > 0:
                    st.sidebar.warning(f"⚠️ {summary['WARNING']} warnings")
                if summary['INFO'] > 0:
                    st.sidebar.info(f"ℹ️ {summary['INFO']} info messages")
                
                # Show detailed validation results in expander
                with st.sidebar.expander("Data Quality Report", expanded=(summary['ERROR'] > 0)):
                    for issue in validation_issues[:20]:  # Show first 20
                        severity_icon = "❌" if issue.severity == "ERROR" else ("⚠️" if issue.severity == "WARNING" else "ℹ️")
                        st.text(f"{severity_icon} {issue.category}: {issue.message}")
                        if issue.transaction_ref:
                            st.caption(f"   Transaction: {issue.transaction_ref}")
                    
                    if len(validation_issues) > 20:
                        st.text(f"... and {len(validation_issues) - 20} more issues")
            else:
                st.sidebar.success("✅ Data quality validation passed")
                
        except Exception as e:
            logger.error(f"Data validation error: {e}", exc_info=True)
            # Continue even if validation fails
    
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
                st.plotly_chart(fig_allocation, width="stretch")
            else:
                st.info("No holdings to display")
        except Exception as e:
            st.error(f"Failed to create allocation chart: {e}")
            logger.error(f"Allocation chart error: {e}", exc_info=True)
    
    with col_right:
        st.subheader("📈 Performance History")
        try:
            # Calculate historical portfolio values (simplified - last 365 days)
            # Note: Full reconstruction is expensive, this is a simplified version
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)
            
            # Filter transactions within date range
            hist_trans = [t for t in transactions if start_date.date() <= t.date.date() <= end_date.date()]
            
            if hist_trans:
                # Group by month for performance
                dates_list = []
                invested_list = []
                value_list = []
                
                # Simple approach: calculate at monthly intervals
                current_date = start_date
                while current_date <= end_date:
                    # Get transactions up to this date
                    trans_until = [t for t in transactions if t.date <= current_date]
                    if trans_until:
                        temp_portfolio = Portfolio(trans_until)
                        temp_value = temp_portfolio.calculate_total_value(prices)
                        
                        dates_list.append(current_date.strftime('%Y-%m'))
                        invested_list.append(float(temp_portfolio.total_invested))
                        value_list.append(float(temp_value))
                    
                    current_date += timedelta(days=30)  # Roughly monthly
                
                if dates_list:
                    fig_performance = create_performance_chart(dates_list, invested_list, value_list)
                    st.plotly_chart(fig_performance, width="stretch")
                else:
                    st.info("Not enough historical data")
            else:
                st.info("No transactions in the last 365 days")
                
        except Exception as e:
            st.error(f"Failed to create performance chart: {e}")
            logger.error(f"Performance chart error: {e}", exc_info=True)
    
    st.divider()
    
    # Holdings table
    st.subheader("📋 Current Holdings")
    try:
        holdings_df = portfolio.get_holdings_summary(prices)
        if not holdings_df.empty:
            # Format for display
            holdings_display = holdings_df.copy()
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
