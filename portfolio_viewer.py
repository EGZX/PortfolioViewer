# -----------------------------------------------------------------------------
# (c) 2026 Andreas Wagner. All Rights Reserved.
#
# This code is part of the Portfolio Viewer project.
# Unauthorized usage or distribution is not permitted.
# -----------------------------------------------------------------------------

"""
Portfolio Viewer - Streamlit Application

A portfolio analysis tool with:
- CSV transaction import with auto-format detection
- (Almost) Live market data from yfinance
- XIRR and absolute return calculations
- Interactive visualizations
"""

import streamlit as st
from datetime import datetime, date
from decimal import Decimal
import pandas as pd
import json
from calculators.portfolio import Portfolio
from calculators.metrics import xirr, calculate_absolute_return, calculate_volatility, calculate_sharpe_ratio, calculate_max_drawdown
from calculators.tax_basis import TaxBasisEngine
from calculators.tax_calculators import get_calculator
from calculators.transaction_store import TransactionStore
from services.market_data import fetch_prices, get_currency_for_ticker, get_fx_rate
from services.market_cache import get_market_cache
from services.corporate_actions import CorporateActionService
from services.data_validator import DataValidator
from services.pipeline import process_data_pipeline, parse_csv_only
from charts.visualizations import create_allocation_donut, create_performance_chart, create_allocation_treemap
from utils.logging_config import setup_logger
from utils.auth import check_authentication, show_logout_button
from ui.styles import APP_STYLE
from ui.components import render_kpi_dashboard
from ui.sidebar import render_sidebar_controls, render_sidebar_status
from ui.utils import mask_currency, mask_currency_precise

logger = setup_logger(__name__)

# Page configuration
st.set_page_config(
    page_title="Portfolio Viewer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown(APP_STYLE, unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=3600)
def get_performance_history_cached(transactions, price_history, start_date, end_date):
    """
    Performance calculation wrapper with caching.
    """
    temp_portfolio = Portfolio(transactions)
    return temp_portfolio.calculate_performance_history_optimized(
        price_history, start_date, end_date
    )

@st.cache_data(show_spinner=False, ttl=3600*12)
def apply_corporate_actions_cached(transactions):
    """
    Cached wrapper for corporate actions (splits).
    """
    corp_actions = CorporateActionService()
    return corp_actions.detect_and_apply_splits(transactions)


def main():
    """Main application entry point."""
    
    # Authentication check
    if not check_authentication():
        st.stop()
    
    show_logout_button()
    
    # Mobile detection logic
    # Priority: Query Param > Session State > User-Agent Detection
    qp_mobile = st.query_params.get("mobile")
    
    if qp_mobile == "true":
        st.session_state.is_mobile = True
    elif qp_mobile == "false":
        st.session_state.is_mobile = False
    elif 'is_mobile' not in st.session_state:
        # Auto-detect from request headers (User-Agent)
        try:
            # Streamlit doesn't expose headers directly, but we can use streamlit_js
            # As fallback, default to desktop
            st.session_state.is_mobile = False
            logger.info("Mobile detection: Defaulting to desktop, use sidebar toggle to override")
        except Exception:
            st.session_state.is_mobile = False
    
    # Force rendering update
    st.markdown('<div id="flush-ghost" style="height:1px; width:1px;"></div>', unsafe_allow_html=True)
    
    # ==========================================
    # SIDEBAR CONTROLS
    # ==========================================
    file_content = render_sidebar_controls()
    
    if file_content is None:
        return

    # ==========================================
    # MAIN DASHBOARD CONTENT
    # ==========================================
    
    # Process Data
    transactions = []
    
    if 'prices_updated' not in st.session_state:
        st.session_state.prices_updated = False

    # Check if using multi-source mode
    if file_content == "MULTI_SOURCE_MODE":
        # Load from TransactionStore
        try:
            with st.spinner("Loading from TransactionStore..."):
                store = TransactionStore()
                transactions = store.get_all_transactions()
                
                if not transactions:
                    st.warning("No transactions in store. Import some files first.")
                    return
                
                # Mark as enriched (already processed when imported)
                st.session_state.enrichment_done = True
                
                # Validation
                validator = DataValidator()
                validation_issues = validator.validate_all(transactions)
                val_summary = validator.get_summary()
                validation_data = (validation_issues, val_summary)
                
                # Check if duplicate review is requested
                if st.session_state.get('show_duplicate_review', False):
                    from ui.duplicate_resolution import render_duplicate_review
                    
                    st.title("🔍 Duplicate Review")
                    duplicate_groups = store.get_pending_duplicate_groups()
                    render_duplicate_review(duplicate_groups, store)
                    
                    # Close button
                    if st.button("✓ Close Review", type="primary"):
                        st.session_state.show_duplicate_review = False
                        st.rerun()
                    
                    return  # Don't show portfolio while reviewing duplicates
                
        except Exception as e:
            st.error(f"Failed to load from TransactionStore: {str(e)}")
            logger.error(f"TransactionStore load error: {e}", exc_info=True)
            return
    else:
        # Single-file mode (legacy)
        # Determine if tx enrichment is requested or already done
        enrich_req = False # Triggered by refresh or initial load
        if not st.session_state.enrichment_done: # If not done, try to enrich
            enrich_req = True
        
        try:
            # Note: logic preserved from original; virtually always tries to enrich if not done.
            if enrich_req or st.session_state.enrichment_done:
                transactions, split_log, fx_conversions = process_data_pipeline(file_content)
                st.session_state.enrichment_done = True
                
                # Run Validation locally (fast, avoids caching pickle issues)
                validator = DataValidator()
                validation_issues = validator.validate_all(transactions)
                val_summary = validator.get_summary()
                validation_data = (validation_issues, val_summary)
                
            else:
                transactions, validation_data = parse_csv_only(file_content)
                split_log = []
                fx_conversions = 0
            
            if not transactions:
                st.error("No valid transactions found.")
                return
                
        except Exception as e:
            st.error(f"Processing Error: {str(e)}")
            # If cache is corrupted, offer to clear it
            if "serialize" in str(e) or "pickle" in str(e):
                 st.warning("Cache corruption detected. Clearing cache recommended.")
                 if st.button("Emergency Clear Cache"):
                     st.cache_data.clear()
                     st.rerun()
            return

    # Build Portfolio
    try:
        portfolio = Portfolio(transactions)
        tickers = portfolio.get_unique_tickers()
    except Exception as e:
        st.error(f"Portfolio Error: {str(e)}")
        return

    # Price Fetching
    cache = get_market_cache()
    if st.session_state.prices_updated:
        with st.spinner("Syncing market data..."):
            prices = fetch_prices(tickers)
        st.session_state.prices_updated = False # Reset after fetching
    else:
        # Load from cache (latest available prices)
        prices = cache.get_prices_batch(tickers, target_date=None)

    # ==========================================
    # SIDEBAR STATUS GRID
    # ==========================================
    render_sidebar_status(transactions, tickers, prices, validation_data)
    
    # Calculate metrics
    with st.spinner("Calculating performance metrics..."):
        try:
            current_value = portfolio.calculate_total_value(prices)
            
            # Calculate Net Worth with FX adjustments
            corrected_net_worth = Decimal(0)
            for h in portfolio.holdings.values():
                if h.shares > 0:
                    val = h.market_value
                    curr = get_currency_for_ticker(h.ticker)
                    if curr != "EUR":
                        try:
                            rate = get_fx_rate(curr, "EUR")
                            val = val * Decimal(str(rate))
                        except Exception:
                            pass
                    corrected_net_worth += val
            
            # Add cash balance
            corrected_net_worth += portfolio.cash_balance
            
            # Update current value
            current_value = corrected_net_worth
            
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
    gain_color = "pos" if total_absolute_gain >= 0 else "neg"
    gain_txt = f"+{total_return_pct:.1f}%" if total_absolute_gain >= 0 else f"{total_return_pct:.1f}%"

    # Fetch historical data
    dates, net_deposits, portfolio_values, cost_basis_values = [], [], [], []
    
    if st.session_state.enrichment_done and transactions:
        # Determine the full date range needed
        earliest_transaction = min(t.date for t in transactions)
        latest_date = datetime.now()
        
        # Get all unique tickers
        all_tickers = set(t.ticker for t in transactions if t.ticker)
        
        # Fetch ALL historical prices once
        price_history = cache.get_historical_prices(all_tickers, earliest_transaction, latest_date)
        
        # Calculate daily portfolio values using the history
        dates, net_deposits, portfolio_values, cost_basis_values = get_performance_history_cached(
            transactions, price_history, earliest_transaction, latest_date
        )

    # Calculate advanced metrics (Vola, Sharpe, Max Drawdown)
    volatility = None
    sharpe_ratio = None
    max_dd = None
    
    if portfolio_values and len(portfolio_values) > 1:
         volatility = calculate_volatility(portfolio_values)
         sharpe_ratio = calculate_sharpe_ratio(portfolio_values)
         max_dd = calculate_max_drawdown(portfolio_values)

    # Prepare KPI Data with Privacy Masking
    kpi_data = [
        {"label": "Net Worth", "value": mask_currency(current_value, st.session_state.privacy_mode)},
        {"label": "Abs Gain", "value": mask_currency(total_absolute_gain, st.session_state.privacy_mode), "delta": gain_txt, "delta_color": gain_color},
        {"label": "XIRR", "value": f"{xirr_value * 100:.1f}%" if xirr_value is not None else "N/A", "delta": None, "delta_color": "pos" if xirr_value and xirr_value > 0 else "neu"},
        {"label": "Realized P&L", "value": mask_currency(portfolio.realized_gains, st.session_state.privacy_mode)},
        {"label": "Invested", "value": mask_currency(portfolio.invested_capital, st.session_state.privacy_mode)},
        {"label": "Holdings", "value": str(len(portfolio.holdings))},
    ]

    # Optimized Layout: Single Container Tile
    st.markdown(render_kpi_dashboard(kpi_data), unsafe_allow_html=True)
    
    # ==================== DASHBOARD CHARTS ====================
    # Container tile for charts
    col1, col2 = st.columns([2, 1])
    
    with col1:
        with st.container(border=True):
            # Render Chart
            st.markdown('<div class="card-title">Performance History</div>', unsafe_allow_html=True)
            
            # Set explicit height
            is_mobile = st.session_state.get('is_mobile', False)
            chart_height = 380 if is_mobile else 520
            
            chart_fig = create_performance_chart(
                dates, net_deposits, portfolio_values, cost_basis_values, 
                title=None,
                privacy_mode=st.session_state.privacy_mode,
                compact_mode=is_mobile
           )
            
            # Explicitly set height
            chart_fig.update_layout(height=chart_height)
            
            st.plotly_chart(
                chart_fig, 
                config={'displayModeBar': 'hover', 'displaylogo': False}
            )

    with col2:
        with st.container(border=True):
            # Simple title - toggle is in sidebar
            st.markdown('<div class="card-title">Asset Allocation</div>', unsafe_allow_html=True)
            
            # Prepare asset allocation data
            allocation_data = []
            for h in portfolio.holdings.values():
                if h.market_value > 0 and h.asset_type.value != 'Cash':
                    # Convert to EUR using current FX rate
                    val_eur = h.market_value
                    currency = get_currency_for_ticker(h.ticker)
                    if currency != "EUR":
                         try:
                             rate = get_fx_rate(currency, "EUR")
                             val_eur = val_eur * Decimal(str(rate))
                         except Exception:
                             pass  # Keep original if fails
                    
                    allocation_data.append({
                        'Ticker': h.ticker, 
                        'Name': h.name, 
                        'Asset Type': h.asset_type.value.capitalize(),
                        'Market Value (EUR)': float(val_eur), 
                        'Quantity': h.shares
                    })
            
            holdings_df = pd.DataFrame(allocation_data)
            
            # Use chart view from sidebar
            is_mobile = st.session_state.get('is_mobile', False)
            chart_height = 340 if is_mobile else 520
            
            if st.session_state.chart_view == "Treemap":
                fig = create_allocation_treemap(
                    holdings_df, 
                    title=None, 
                    privacy_mode=st.session_state.privacy_mode,
                    compact_mode=is_mobile
                )
            else:
                fig = create_allocation_donut(
                    holdings_df, 
                    title=None, 
                    privacy_mode=st.session_state.privacy_mode,
                    compact_mode=is_mobile
                )
            
            # Explicitly set height
            fig.update_layout(height=chart_height)
            
            st.plotly_chart(
                fig, 
                config={'displayModeBar': 'hover', 'displaylogo': False}
            )
    
    
    # Spacer to separate Charts from Tabs
    st.markdown('<div style="margin-bottom: 1.5rem;"></div>', unsafe_allow_html=True)
    
    # ==================== DATA TABLES & METRICS (TABS) ====================
    tab1, tab2, tab3, tab4 = st.tabs(["Holdings", "Metrics", "Transactions", "Tax"])
    
    # ========== TAB 1: HOLDINGS ==========
    with tab1:
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
            st.empty()  # Placeholder
        
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
                    holdings_display['Shares'] = holdings_display['Shares'].apply(lambda x: f"{x:.4f}" if not st.session_state.privacy_mode else "••••")
                    holdings_display['Avg Cost (EUR)'] = holdings_display['Avg Cost (EUR)'].apply(lambda x: mask_currency_precise(x, st.session_state.privacy_mode))
                    holdings_display['Current Price (EUR)'] = holdings_display['Current Price (EUR)'].apply(lambda x: f"€{x:.2f}") 
                    
                    holdings_display['Market Value (EUR)'] = holdings_display['Market Value (EUR)'].apply(lambda x: mask_currency_precise(x, st.session_state.privacy_mode))
                    holdings_display['Allocation %'] = holdings_display['Allocation %'].apply(lambda x: f"{x:.2f}%")
                    holdings_display['Gain/Loss (EUR)'] = holdings_display['Gain/Loss (EUR)'].apply(lambda x: mask_currency_precise(x, st.session_state.privacy_mode))
                    holdings_display['Gain %'] = holdings_display['Gain %'].apply(lambda x: f"{x:.2f}%")
                    
                    st.dataframe(
                        holdings_display,
                        width='stretch',
                        hide_index=True,
                        height=400
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
    
    # ========== TAB 2: DETAILED METRICS ==========
    with tab2:
        detailed_metrics = [
            {"label": "Cash Balance", "value": mask_currency_precise(portfolio.cash_balance, st.session_state.privacy_mode)},
            {"label": "Cost Basis", "value": mask_currency(holdings_cost_basis, st.session_state.privacy_mode)},
            {"label": "Total Dividends", "value": mask_currency_precise(portfolio.total_dividends, st.session_state.privacy_mode)},
            {"label": "Total Interest", "value": mask_currency_precise(portfolio.total_interest, st.session_state.privacy_mode)},
            {"label": "Total Fees", "value": mask_currency_precise(portfolio.total_fees, st.session_state.privacy_mode)},
            {"label": "Transactions", "value": str(len(transactions))},
            {"label": "Volatility (Ann.)", "value": f"{volatility*100:.1f}%" if volatility is not None else "N/A"},
            {"label": "Sharpe Ratio", "value": f"{sharpe_ratio:.2f}" if sharpe_ratio is not None else "N/A"},
            {"label": "Max Drawdown", "value": f"{max_dd*100:.1f}%" if max_dd is not None else "N/A", "delta": None, "delta_color": "neg"}
        ]
        
        # Render using the same KPI dashboard style
        st.markdown(render_kpi_dashboard(detailed_metrics, title=None), unsafe_allow_html=True)
    
    # ========== TAB 3: TRANSACTION HISTORY ==========
    with tab3:
        try:
            # Create transaction history DataFrame
            trans_data = []
            for trans in sorted(transactions, key=lambda t: t.date, reverse=True):
                # Handle Display Logic
                ticker_disp = trans.ticker or '-'
                asset_type_disp = trans.asset_type.value if hasattr(trans, 'asset_type') else 'Unknown'
                
                # Interest / Cash handling
                if trans.type.value == "Interest":
                     if ticker_disp == '-': ticker_disp = "CASH"
                     if asset_type_disp == "Unknown": asset_type_disp = "Cash"

                trans_data.append({
                    'Date': trans.date.strftime('%Y-%m-%d'),
                    'Type': trans.type.value,
                    'Ticker': ticker_disp,
                    'Name': trans.name or '-',
                    'Asset Type': asset_type_disp,
                    'Shares': float(trans.shares) if trans.shares != 0 else 0.0,
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
                    filtered_df = filtered_df[filtered_df['Ticker'] != '-']
                elif selected_asset_filter == 'All':
                    pass
                else:
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
    
    # ========== TAB 4: TAX ==========
    with tab4:
        # st.markdown("### Tax Reporting (Austrian KESt)") # Removed header
        
        # Tax settings
        col1, col2, col3 = st.columns([2, 5, 2])
        
        with col1:
            current_year = datetime.now().year
            available_years = list(range(current_year, current_year - 10, -1))
            selected_year = st.selectbox(
                "Tax Year",
                options=available_years,
                index=0
            )
            
        with col2:
            jurisdiction_options = ["Austria"] # Future: Germany, US
            selected_jurisdiction = st.selectbox(
                 "Tax Jurisdiction",
                 options=jurisdiction_options,
                 index=0,
                 help="Select the country for tax rules application"
            )
        
        with col3:
            strategy_index = 1 # Default to WeightedAverage (1) as it's standard for Austria
            strategy = st.selectbox(
                "Lot Matching",
                options=["FIFO", "WeightedAverage"],
                index=strategy_index
            )
        
        try:
            # Process transactions through Tax Basis Engine
            with st.spinner("Calculating tax liability..."):
                engine = TaxBasisEngine(transactions, matching_strategy=strategy)
                engine.process_all_transactions()
                
                # Get realized events for selected year
                start_date = date(selected_year, 1, 1)
                end_date = date(selected_year, 12, 31)
                events = engine.get_realized_events(start_date, end_date)
                
                # Calculate tax liability
                jurisdiction_map = {"Austria": "AT"}
                country_code = jurisdiction_map.get(selected_jurisdiction, "AT")
                calculator = get_calculator(country_code)
                liability = calculator.calculate_tax_liability(events, selected_year)
            
            if not events:
                st.info(f"No taxable events found for {selected_year}. Import transactions or select a different year.")
            else:
                # === SUMMARY KPIs ===
                tax_kpis = [
                    {
                        "label": "Total Realized Gain",
                        "value": mask_currency(liability.total_realized_gain, st.session_state.privacy_mode),
                        "delta": None,
                        "delta_color": "pos" if liability.total_realized_gain > 0 else "neg"
                    },
                    {
                        "label": "Taxable Gain",
                        "value": mask_currency(liability.taxable_gain, st.session_state.privacy_mode),
                    },
                    {
                        "label": "Tax Owed (27.5%)",
                        "value": mask_currency(liability.tax_owed, st.session_state.privacy_mode),
                        "delta": None,
                        "delta_color": "neg"
                    },
                    {
                        "label": "Taxable Events",
                        "value": str(len(events))
                    },
                ]
                
                st.markdown(render_kpi_dashboard(tax_kpis, title=None), unsafe_allow_html=True)
                
                # === BREAKDOWN ===
                st.markdown("#### Tax Report Breakdown")
                
                breakdown_data = []
                # Identify special summary keys to exclude from list (as they are in KPIs)
                summary_keys = {"total_gains", "total_losses", "net_taxable_gain", "tax_owed", "tax_rate"}
                
                for key, value in liability.breakdown.items():
                    if key not in summary_keys:
                        breakdown_data.append({
                            "Category": key,
                            "Amount (EUR)": mask_currency_precise(value, st.session_state.privacy_mode)
                        })
                
                if breakdown_data:
                    # Sort to keep Kz in order if possible or just alpha
                    breakdown_data.sort(key=lambda x: x["Category"])
                    
                    st.dataframe(
                        pd.DataFrame(breakdown_data),
                        width='stretch',
                        hide_index=True
                    )
                
                # === DETAILED TAX EVENTS ===
                st.markdown("#### Detailed Tax Events")
                
                events_data = []
                for event in sorted(events, key=lambda e: e.date_sold, reverse=True):
                    # Determine clear types
                    event_type = "Sell"
                    asset_type = event.asset_type
                    ticker_disp = event.ticker
                    
                    if event.quantity_sold == 0:
                        # Income Event
                        if event.notes and "Interest" in event.notes:
                            event_type = "Interest"
                            asset_type = "Cash"
                            if not ticker_disp or ticker_disp == "None":
                                ticker_disp = "CASH"
                        elif event.notes and "Dividend" in event.notes:
                            event_type = "Dividend"
                        else:
                            event_type = "Income"
                    
                    # Fix "Unknown" asset type if it looks like Cash/Interest
                    if asset_type == "Unknown" and event_type == "Interest":
                        asset_type = "Cash"

                    events_data.append({
                        "Date": event.date_sold.strftime("%Y-%m-%d"),
                        "Type": event_type,
                        "Ticker": ticker_disp,
                        "Asset": asset_type,
                        "Qty": float(event.quantity_sold) if event.quantity_sold > 0 else "",
                        "Proceeds (EUR)": mask_currency_precise(float(event.proceeds_base), st.session_state.privacy_mode),
                        "Cost (EUR)": mask_currency_precise(float(event.cost_basis_base), st.session_state.privacy_mode),
                        "Gain/Loss (EUR)": mask_currency_precise(float(event.realized_gain), st.session_state.privacy_mode),
                        "Days": event.holding_period_days if event.holding_period_days > 0 else "",
                        "Acquired": event.date_acquired.strftime("%Y-%m-%d"),
                    })
                
                events_df = pd.DataFrame(events_data)
                
                st.dataframe(
                    events_df,
                    width='stretch',
                    hide_index=True,
                    height=400
                )
                
                # === TAX ASSUMPTIONS & NOTES ===
                with st.expander("📋 Tax Calculation Assumptions"):
                    st.markdown("**Jurisdiction:** " + liability.jurisdiction)
                    st.markdown("**Calculator Version:** " + liability.calculator_version)
                    st.markdown("**Calculation Date:** " + liability.calculation_date.strftime("%Y-%m-%d"))
                    st.markdown("")
                    st.markdown("**Assumptions:**")
                    for assumption in liability.assumptions:
                        st.markdown(f"- {assumption}")
                    
                    if liability.notes:
                        st.markdown("")
                        st.markdown("**Notes:**")
                        st.markdown(f"- {liability.notes}")
                
                # === EXPORT OPTIONS ===
                st.markdown("#### Export")
                
                export_col1, export_col2 = st.columns(2)
                
                with export_col1:
                    # CSV Export
                    csv_data = events_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Events CSV",
                        data=csv_data,
                        file_name=f"tax_events_{selected_year}_AT.csv",
                        mime="text/csv"
                    )
                
                with export_col2:
                    # JSON Export (full liability)
                    json_data = {
                        "jurisdiction": liability.jurisdiction,
                        "tax_year": liability.tax_year,
                        "total_realized_gain": float(liability.total_realized_gain),
                        "taxable_gain": float(liability.taxable_gain),
                        "tax_owed": float(liability.tax_owed),
                        "breakdown": {k: float(v) for k, v in liability.breakdown.items()},
                        "assumptions": liability.assumptions,
                        "notes": liability.notes,
                        "calculator_version": liability.calculator_version,
                        "calculation_date": liability.calculation_date.strftime("%Y-%m-%d")
                    }
                    
                    st.download_button(
                        label="📥 Download Full Report JSON",
                        data=json.dumps(json_data, indent=2),
                        file_name=f"tax_report_{selected_year}_AT.json",
                        mime="application/json"
                    )
        
        except Exception as e:
            st.error(f"Tax calculation error: {str(e)}")
            logger.error(f"Tax reporting error: {e}", exc_info=True)
            
            # Show debug info
            with st.expander("🔍 Debug Information"):
                st.code(str(e))
                st.markdown("**Tips:**")
                st.markdown("- Ensure transactions have been imported")
                st.markdown("- Check that ISIN/ticker data is enriched")
                st.markdown("- Verify transaction types are recognized")


if __name__ == "__main__":
    main()
