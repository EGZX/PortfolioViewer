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
from parsers.enhanced_transaction import Transaction, AssetType  # Import enhanced model
from calculators.portfolio import Portfolio
from calculators.metrics import xirr, calculate_absolute_return, calculate_volatility, calculate_sharpe_ratio, calculate_max_drawdown
from services.market_data import fetch_prices, fetch_historical_prices, get_currency_for_ticker, get_fx_rate
from services.corporate_actions import CorporateActionService
from services.fx_rates import FXRateService
from services.data_validator import DataValidator, ValidationIssue  # Data quality
from charts.visualizations import create_allocation_donut, create_performance_chart
from utils.logging_config import setup_logger
from utils.auth import check_authentication, show_logout_button
from services.market_cache import get_market_cache

logger = setup_logger(__name__)


@st.cache_data(show_spinner="Loading chart data...", ttl=3600)
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
        
        # Validation moved OUT of cached function to avoid pickling errors
        # (ValidationIssue objects were likely causing serialization failures)
        
        return transactions, split_log, fx_conversions
        
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
# Custom CSS - Cyber-Fintech Professional
st.markdown("""
<style>
    /* Import Professional Fonts - RESTORED */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    /* Main Container Padding Override */
    .block-container {
        padding-top: 5rem !important; /* Force space below hamburger menu/running man */
        padding-bottom: 3rem !important;
    }
    
    /* Design Tokens - Deep Space / FinTech */
    :root {
        --bg-color: #0d1117;        /* Deep Space Blue */
        --sidebar-bg: #161b22;      /* Slate Blue Dark */
        --card-bg: rgba(22, 27, 34, 0.75); /* Semi-transparent blue-grey */
        --card-border: rgba(48, 54, 61, 0.8);     /* Subtle structural border */
        --text-primary: #f0f6fc;    /* High-contrast white/blue tint */
        --text-secondary: #8b949e;  /* HUD dimmed text */
        --accent-primary: #3b82f6;  /* System Blue */
        --accent-glow: rgba(59, 130, 246, 0.25); /* Subtle bloom */
        --accent-secondary: #6366f1; 
        --glass-bg: rgba(30, 35, 41, 0.7); /* Restored Glass */
    }
    
    /* Global App Styling with Radial Gradient */
    .stApp {
        background-color: var(--bg-color);
        /* Richer blue-black gradient for depth */
        background-image: radial-gradient(circle at 50% -20%, #1e293b 0%, #0d1117 80%);
        color: var(--text-primary);
        font-family: 'Inter', sans-serif;
    }

    /* Custom Scrollbar for Cyberpunk Immersion */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    ::-webkit-scrollbar-track {
        background: var(--bg-color);
    }
    ::-webkit-scrollbar-thumb {
        background: #30363d;
        border-radius: 5px;
        border: 2px solid var(--bg-color);
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #58a6ff; /* Accent color on hover */
    }
    
    /* Cyber-Tech Headers */
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
        text-shadow: 0 0 20px rgba(59, 130, 246, 0.4); /* Dynamic Glow */
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
    /* Section Headers */
    h1, h2, h3 {
        font-family: 'JetBrains Mono', monospace !important;
        text-transform: uppercase !important;
        letter-spacing: -0.02em !important;
    }
    
    h3 {
        font-size: 1.0rem !important;
        font-weight: 700 !important;
        color: var(--text-primary) !important;
        border-left: 3px solid var(--accent-primary);
        padding-left: 12px;
        margin-top: 2rem !important;
        margin-bottom: 1.5rem !important;
        background: linear-gradient(90deg, rgba(59, 130, 246, 0.05) 0%, transparent 50%);
        padding-top: 6px;
        padding-bottom: 6px;
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
        background-color: rgba(13, 17, 23, 0.7); /* Glassy Blue-Black */
        backdrop-filter: blur(12px); /* Dynamic Blur */
        border: 1px solid rgba(59, 130, 246, 0.15); /* Subtle Blue Border */
        border-radius: 6px; 
        padding: 1.5rem;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2); /* Soft depth */
        margin-bottom: 2rem; 
        margin-top: 1rem; 
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
        padding: 0.8rem;
        border-right: 1px solid rgba(255,255,255,0.05); /* Subtle separator */
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-height: 80px;
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
        font-size: 0.7rem;
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
        font-size: 1.15rem;
        font-weight: 700;
        color: #ffffff; /* Absolute White for data */
        line-height: 1;
        letter-spacing: -0.02em;
        font-variant-numeric: tabular-nums; /* Stable alignment */
    }
    
    /* Animation: Subtle Pulse for Net Worth */
    @keyframes pulse-blue {
        0% { text-shadow: 0 0 0 rgba(59, 130, 246, 0); }
        50% { text-shadow: 0 0 10px rgba(59, 130, 246, 0.5); }
        100% { text-shadow: 0 0 0 rgba(59, 130, 246, 0); }
    }
    
    .kpi-item:first-child .kpi-value {
        color: var(--accent-primary) !important;
        animation: pulse-blue 3s infinite ease-in-out;
    }
    
    /* Make Abs Gain (2nd item) stand out if needed, or all equal */

    
    /* Sidebar Headers */
    /* Sidebar Styling - Compact & Professional */
    [data-testid="stSidebar"] {
        background-color: #0d1117 !important;
        border-right: 1px solid var(--card-border);
    }
    
    [data-testid="stSidebar"] .block-container {
        padding-top: 3rem; /* Increased top padding matching main */
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
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.2em;
        margin-top: 2rem !important;
        margin-bottom: 1rem !important;
        padding-left: 0 !important;
        border-left: none !important;
        color: #7d8590 !important; /* Muted tech gray */
        font-weight: 700 !important;
    }

    /* Professional Control Surface Inputs */
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #0d1117 !important;
        border: 1px solid #30363d !important;
        color: #c9d1d9 !important;
    }
    
    [data-testid="stSidebar"] button {
        border-color: #30363d !important;
        background-color: #21262d !important;
        color: #c9d1d9 !important;
        font-size: 0.7rem !important;
    }
    
    [data-testid="stSidebar"] button:hover {
        border-color: #8b949e !important;
        background-color: #30363d !important;
        color: #ffffff !important;
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
    /* Primary Buttons (Login, Refresh) */
    .stButton>button {
        background-color: #21262d;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: 4px;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        padding: 0.6rem 1rem;
        box-shadow: 0 1px 0 rgba(27,31,36,0.04);
    }
    
    .stButton>button:hover {
        background-color: #30363d;
        border-color: #8b949e;
        color: #ffffff;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
    }

    .stButton>button:active {
        background-color: #21262d;
        transform: translateY(0);
    }
    
    /* Primary Action Override (Login) */
    button[kind="primary"] {
        background-color: var(--accent-primary) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
    }
    
    button[kind="primary"]:hover {
        box-shadow: 0 0 15px var(--accent-glow) !important;
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
    
    /* Dataframes - Precision Grid */
    [data-testid="stDataFrame"] {
        border: 1px solid var(--card-border) !important;
        border-radius: 4px;
        background-color: #0d1117 !important; /* Apply background to main wrapper only */
    }
    
    th {
        background-color: #161b22 !important;
        color: var(--text-secondary) !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        border-bottom: 1px solid #30363d !important;
    }
    
    td {
        color: #ffffff !important; /* Force White Text */
        font-family: 'JetBrains Mono', monospace; /* Reverted to Tech Font */
        font-size: 0.8rem;
        border-bottom: 1px solid #21262d !important;
        font-variant-numeric: tabular-nums; /* Aligned numbers */
    }
    
    /* RIGID ALERTS (Terminal Style) */
    [data-testid="stAlert"] {
        background-color: #0d1117 !important;
        border: 1px solid var(--card-border) !important;
        border-left-width: 4px !important;
        border-radius: 4px !important;
        color: var(--text-primary) !important;
    }
    
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
         font-family: 'JetBrains Mono', monospace !important;
         font-size: 0.85rem !important;
    }
    
    /* Chart Containers */
    /* Chart Containers */
    [data-testid="stPlotlyChart"] {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    

    
    /* Container Borders (st.container(border=True)) */
    /* Container Borders - Instrument Panel Cards */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid rgba(60, 66, 75, 0.5) !important;
        background-color: rgba(13, 17, 23, 0.6) !important; /* Semi-transparent */
        backdrop-filter: blur(8px); /* Subtle blur for dashboard cards */
        border-radius: 6px !important;
        padding: 1.5rem !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
        margin-bottom: 1rem !important;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }

    /* Active Component Border */
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(59, 130, 246, 0.4) !important; /* Blue highlight */
        transform: translateY(-2px); /* Slight lift */
        box-shadow: 0 10px 30px rgba(0,0,0,0.2) !important;
    }
    
    /* Subtle Hover Effect on Cards */
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(96, 165, 250, 0.4) !important;
        box-shadow: 
            0 8px 16px rgba(0,0,0,0.15),
            0 0 30px rgba(59, 130, 246, 0.1) !important;
        transform: translateY(-2px);
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

    /* ============================================= */
    /* ============================================= */
    /* RESPONSIVE DESIGN (MOBILE/TABLET ADAPTATIONS) */
    /* ============================================= */
    
    /* Tablet/Small Laptop (Max Width: 1024px) */
    @media only screen and (max-width: 1024px) {
        /* KPI Grid - 3 columns */
        .kpi-grid {
            grid-template-columns: repeat(3, 1fr);
        }
        .kpi-item {
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .kpi-item:nth-child(3n) {
            border-right: none; 
        }
        .kpi-item:nth-child(n+4) {
            border-bottom: none;
        }
    }
    
    /* Mobile (Max Width: 768px) */
    @media only screen and (max-width: 768px) {
        
        /* 1. FORCE COLUMN STACKING */
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 auto !important;
            min-width: 100% !important;
        }

        /* 2. KPI GRID - 2 Columns */
        .kpi-grid {
            grid-template-columns: repeat(2, 1fr);
        }
        .kpi-item {
            border-right: 1px solid rgba(255,255,255,0.05);
            border-bottom: 1px solid rgba(255,255,255,0.05);
            padding: 0.5rem;
            min-height: 70px;
        }
        .kpi-item:nth-child(2n) { border-right: none; }
        .kpi-item:nth-child(n+5) { border-bottom: none; }
        .kpi-item:nth-child(3n) { border-right: 1px solid rgba(255,255,255,0.05); }
        .kpi-item:nth-child(3), .kpi-item:nth-child(4) { 
            border-bottom: 1px solid rgba(255,255,255,0.05); 
        }
        
        /* 3. COMPACT SPACING */
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 1rem !important;
        }
        .card-title {
            margin-bottom: 0.5rem !important;
            font-size: 1.0rem;
        }
        
        /* 4. TYPOGRAPHY */
        .main-header { font-size: 1.4rem; }
        .sub-header { font-size: 0.7rem; margin-bottom: 1.5rem; }
        .kpi-value { font-size: 1.0rem; }
        .metric-label { font-size: 0.65rem; }
        
        /* 5. MOBILE CHART ADJUSTMENTS - Python controls size via compact_mode */
        /* No need for aggressive CSS overrides anymore */
    }
    
</style>
""", unsafe_allow_html=True)


def render_kpi_dashboard(metrics, title="Key Performance Indicators"):
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
    if title:
        html += f'<div class="kpi-header">{title}</div>'
    html += '<div class="kpi-grid">'
    html += items_html
    html += '</div></div>'
    
    return html

@st.cache_data(show_spinner=False, ttl=3600)
def get_performance_history_cached(transactions, price_history, start_date, end_date):
    """
    Cached wrapper for portfolio history calculation.
    This avoids re-calculating the daily path on every rerun if data hasn't changed.
    """
    # Create a temporary portfolio instance to access the logic
    # Note: This does trigger one state reconstruction, but we save the expensive daily loop
    temp_portfolio = Portfolio(transactions)
    return temp_portfolio.calculate_performance_history_optimized(
        price_history, start_date, end_date
    )

@st.cache_data(show_spinner=False, ttl=3600*12)
def apply_corporate_actions_cached(transactions):
    """
    Cached wrapper for corporate actions (splits).
    This is the most expensive operation on startup (40s+).
    """
    corp_actions = CorporateActionService()
    # Ensure we don't modify the input list in place if it's cached from somewhere else (safety copy)
    # Although apply_splits usually returns a new list or modifies. 
    # Streamlit cache returns a copy by default on subsequent calls, but first run modifies?
    # Safe to pass as is.
    return corp_actions.detect_and_apply_splits(transactions)


def main():
    """Main application entry point."""
    
    # Authentication check
    if not check_authentication():
        st.stop()
        
    # FLUSH GHOST: Force a rendering update to clear the login screen before processing starts
    st.markdown('<div id="flush-ghost" style="height:1px; width:1px;"></div>', unsafe_allow_html=True)
    
    show_logout_button()
    
    # Header - Cyber Tech
    # Header - Excised for Data Density
    # (Vertical space reclaimed)
    
    # ==========================================
    # SIDEBAR: COMPACT & CLEAN
    # ==========================================
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

        st.markdown("### OPERATIONS")
        
        # Action Buttons - Clean Text
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
        
        # Privacy Mode Toggle
        if 'privacy_mode' not in st.session_state:
            st.session_state.privacy_mode = False
            
        privacy_mode = st.toggle("Privacy Mode", value=st.session_state.privacy_mode)
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
            
            # CRITICAL: Re-calculate Net Worth with proper FX conversion for display
            # (The portfolio.calculate_total_value uses raw prices to prevent history spikes)
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
            
            # Update current_value to use the FX-adjusted total for the KPI
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

    # ==================== FETCH ALL HISTORICAL DATA ONCE ====================
    # This runs once and is cached - timeframe changes only filter the data
    # ONLY if transactions have been enriched (to avoid split API calls)
    
    dates, net_deposits, portfolio_values, cost_basis_values = [], [], [], []
    
    if st.session_state.enrichment_done and transactions:
        # Determine the full date range needed
        earliest_transaction = min(t.date for t in transactions)
        latest_date = datetime.now()
        
        # Get all unique tickers
        all_tickers = set(t.ticker for t in transactions if t.ticker)
        
        # Fetch ALL historical prices once (cached by Streamlit)
        price_history = cache.get_historical_prices(all_tickers, earliest_transaction, latest_date)
        
        # Calculate daily portfolio values using the history (CACHED)
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
    
    # st.divider() # Removed separator line

    # ==================== DASHBOARD CHARTS ====================
    
    # ==================== DASHBOARD CHARTS ====================
    # Container tile for charts
    # ==================== DASHBOARD CHARTS ====================
    # Split Layout: Two separate tiles for cleaner visual distinction
    col1, col2 = st.columns([2, 1])
    
    with col1:
        with st.container(border=True):
            # Render Chart with FULL data (filtering handled by Plotly native Range Selector)
            # Layout changed: Title Moved OUTSIDE of chart to prevent Mobile Overlap
            st.markdown('<div class="card-title">Performance History</div>', unsafe_allow_html=True)
            
            chart_fig = create_performance_chart(
                dates, net_deposits, portfolio_values, cost_basis_values, 
                title=None, # Title handled externally for responsiveness
                privacy_mode=st.session_state.privacy_mode
            )
            st.plotly_chart(chart_fig, width='stretch')

    with col2:
        with st.container(border=True):
            # Layout changed: Title Moved OUTSIDE of chart
            st.markdown('<div class="card-title">Asset Allocation</div>', unsafe_allow_html=True)
            
            # Filter OUT Cash and Apply FX Conversion for accurate allocation
            allocation_data = []
            for h in portfolio.holdings.values():
                if h.market_value > 0 and h.asset_type != AssetType.CASH:
                    # Convert to EUR using current FX rate
                    val_eur = h.market_value
                    currency = get_currency_for_ticker(h.ticker)
                    if currency != "EUR":
                         try:
                             rate = get_fx_rate(currency, "EUR")
                             val_eur = val_eur * Decimal(str(rate))
                         except Exception:
                             pass # Keep original if fails
                    
                    allocation_data.append({
                        'Ticker': h.ticker, 
                        'Name': h.name, 
                        'Market Value (EUR)': float(val_eur), 
                        'Quantity': h.shares
                    })
            
            holdings_df = pd.DataFrame(allocation_data)
            
            donut_fig = create_allocation_donut(
                holdings_df, 
                title=None, # Title handled externally
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
                    holdings_display['Allocation %'] = holdings_display['Allocation %'].apply(lambda x: f"{x:.2f}%")
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
    # Reverted to Expander per user request
    # Additional info
    # Reverted to Expander per user request
    with st.expander("Detailed Metrics", expanded=True):
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
        
        # Render using the same style as KPI board, but with no title (handled by expander) or custom title
        # User asked for "Detailed Metrics" to be same size.
        # We can pass title=None and let Expander be the container, OR render the title inside.
        # Expander header is styled differently. 
        # Let's simple render the grid.
        st.markdown(render_kpi_dashboard(detailed_metrics, title=None), unsafe_allow_html=True)
    
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
