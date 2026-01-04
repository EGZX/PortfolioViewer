# -----------------------------------------------------------------------------
# (c) 2026 Andreas Wagner. All Rights Reserved.
#
# This code is part of the Portfolio Viewer project.
# Unauthorized usage or distribution is not permitted.
# -----------------------------------------------------------------------------

"""
Application Styles and Design Tokens
"""

APP_STYLE = """
<style>
    /* Import Professional Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap');
    
    /* Main Container Padding Override */
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 3rem !important;
    }
    
    /* ========================================== */
    /* DESIGN TOKENS                              */
    /* ========================================== */
    
    :root {
        /* Color System - Matte Moonlit Aesthetic */
        --bg-color: #12161f;
        --sidebar-bg: rgba(23, 28, 38, 0.85);
        --card-bg: rgba(28, 34, 45, 0.45);
        --card-border: rgba(75, 125, 163, 0.35);
        --text-primary: #ecf3fa;
        --text-secondary: #a8b5c8;
        --accent-primary: #4B7DA3;
        --accent-glow: rgba(75, 125, 163, 0.3);
        --accent-secondary: #1F456E;
        --glass-bg: rgba(30, 38, 48, 0.4);
        
        /* Palette - Natural Moonlight */
        --steel-blue: #5a7a8f;
        --slate-teal: #527a85;
        --frost-blue: #6b8a9d;
        --mist-gray: #7a8c9a;
        
        /* Typography System */
        --font-primary: 'Inter', sans-serif;
        --font-mono: 'JetBrains Mono', monospace;
        
        --font-size-xs: 0.65rem;     /* Mobile labels, small text */
        --font-size-sm: 0.75rem;     /* Standard labels, filter labels */
        --font-size-base: 0.85rem;   /* Body text, inputs */
        --font-size-md: 1.0rem;      /* Card titles (mobile) */
        --font-size-lg: 1.1rem;      /* Card titles, KPI headers, expanders */
        --font-size-xl: 1.25rem;     /* KPI values */
        --font-size-2xl: 1.4rem;     /* Metric values */
        --font-size-3xl: 1.8rem;     /* Main headers */
        
        --font-weight-normal: 400;
        --font-weight-medium: 500;
        --font-weight-semibold: 600;
        --font-weight-bold: 700;
        
        /* Spacing Scale */
        --spacing-xs: 0.5rem;
        --spacing-sm: 1rem;
        --spacing-md: 1.5rem;
        --spacing-lg: 1.75rem;
        --spacing-xl: 3rem;
        
        /* Border Radius */
        --radius-sm: 4px;
        --radius: 10px;
        
        /* Gradient Separator */
        --separator-gradient: linear-gradient(180deg, 
            rgba(90, 122, 143, 0.5) 0%,
            rgba(82, 122, 133, 0.35) 50%,
            rgba(107, 138, 157, 0.25) 100%
        );
    }
    
    /* Global App Styling with Organic Nebula Background */
    .stApp {
        background-color: #0d1117; /* Deep Navy Abyss (More Blue Base) */
        /* Organic Nebula Pattern: "Perfect Moonlit Foggy Sea" */
        background-image: 
            /* 1. The Moon Source (Extended Reach / Shallower Drop) */
            radial-gradient(circle at 50% -10%, rgba(170, 190, 210, 0.15) 0%, transparent 80%),
            
            /* 2. The Foggy Haze (Wider / softer) */
            radial-gradient(ellipse at 50% 25%, rgba(89, 120, 142, 0.10) 0%, transparent 75%),
            
            /* 3. Deep Vignette (Dark Sides - Pushed out further) */
            linear-gradient(90deg, rgba(13, 17, 23, 0.95) 0%, transparent 20%, transparent 80%, rgba(13, 17, 23, 0.95) 100%);
            
        background-size: 100% 100%;
        color: var(--text-primary);
        font-family: 'Inter', sans-serif;
    }

    /* Custom Scrollbar */
    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    ::-webkit-scrollbar-track {
        background: var(--bg-color);
    }
    /* Design Tokens - Deep Space / FinTech */
    :root {
        /* ... existing vars ... */
        --radius: 4px; /* Standardized small radius */
    }

    /* ... */

    ::-webkit-scrollbar-thumb {
        background: #30363d;
        border-radius: 10px;
        border: 2px solid var(--bg-color);
    }
    
    /* ... */

    .cyber-metric-container {
        /* ... */
        border-radius: 10px;
        /* ... */
    }

    /* ... */

    .kpi-board {
        /* ... */
        border-radius: 10px; 
        /* ... */
    }

    /* ... */
    
    /* Sidebar Styling */
    /* ... */

    .streamlit-expanderHeader {
        /* ... */
        border-radius: 10px;
        /* ... */
    }
    
    .stSelectbox > div > div {
        /* ... */
        border-radius: 10px;
        /* ... */
    }

    .stButton>button {
        /* ... */
        border-radius: 10px;
        /* ... */
    }
    
    [data-testid="stDataFrame"] {
        border: 1px solid var(--card-border) !important;
        border-radius: 10px;
        background-color: #0d1117 !important;
        overflow: hidden;
    }
    
    [data-testid="stAlert"] {
        /* ... */
        border-radius: 4px !important;
        /* ... */
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        /* ... */
        border-radius: 4px !important;
        /* ... */
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #58a6ff; /* Accent color on hover */
    }
    
    /* ========================================== */
    /* TYPOGRAPHY                                 */
    /* ========================================== */
    
    /* Main Headers */
    .main-header {
        font-family: var(--font-mono);
        font-size: var(--font-size-3xl);
        font-weight: var(--font-weight-semibold);
        color: var(--text-primary);
        letter-spacing: -0.02em;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        text-shadow: 0 0 20px rgba(59, 130, 246, 0.4);
    }
    
    .sub-header {
        font-family: var(--font-primary);
        font-size: var(--font-size-base);
        font-weight: var(--font-weight-semibold);
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.15em;
        margin-bottom: 2rem;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    /* Section Headers (h1, h2, h3) */
    h1, h2, h3 {
        font-family: var(--font-mono) !important;
        text-transform: uppercase !important;
        letter-spacing: -0.02em !important;
    }
    
    h3 {
        font-size: var(--font-size-lg) !important;
        font-weight: var(--font-weight-bold) !important;
        color: var(--text-primary) !important;
        border-left: 3px solid var(--accent-primary);
        padding-left: 12px;
        margin-top: 0 !important;
        margin-bottom: var(--spacing-md) !important;
        background: linear-gradient(90deg, var(--accent-glow) 0%, transparent 50%);
        padding-top: 6px;
        padding-bottom: 6px;
    }
    
    /* CUSTOM METRIC CARD CSS */
    .cyber-metric-container {
        display: flex;
        flex-direction: column;
        background-color: #1e2329; /* card-bg */
        border: 1px solid #2b313a; /* card-border */
        border-top: 2px solid #2b313a;
        border-left: 3px solid #3b82f6; /* accent-primary */
        border-radius: 10px;
        padding: 12px 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        position: relative;
        overflow: hidden;
        margin-bottom: 1.5px;
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
        font-family: var(--font-primary);
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        color: var(--text-secondary);
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
        font-family: var(--font-mono);
        font-size: var(--font-size-2xl);
        font-weight: var(--font-weight-bold);
        color: var(--text-primary);
        line-height: 1.1;
    }
    
    .metric-delta {
        font-family: var(--font-mono);
        font-size: var(--font-size-base);
        font-weight: var(--font-weight-semibold);
        padding: 2px 8px;
        border-radius: var(--radius);
        display: inline-flex;
        align-items: center;
        white-space: nowrap;
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
        border: 1px  solid rgba(156, 163, 175, 0.2);
    }
    
    /* Section Separation Line */
    hr {
        margin-top: 2rem;
        margin-bottom: 2rem;
        border: 0;
        border-top: 1px solid #2b313a;
    }
    
    .kpi-board {
        background-color: transparent !important;
        border: 1px solid rgba(60, 66, 75, 1) !important;
        backdrop-filter: blur(8px);
        border-radius: 10px; 
        padding: 1rem; /* Compact padding */
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
        margin-bottom: 2.5rem !important;
        margin-top: var(--spacing-sm);
        animation: fadeIn 0.5s ease-out;
    }
    
    /* Remove nested container styling when inside expander */
    [data-testid="stExpanderDetails"] .kpi-board {
        border: none !important;
        padding: 0.5rem 0 !important;
        margin-top: 0 !important;
        margin-bottom: 0 !important;
        box-shadow: none !important;
        backdrop-filter: none !important;
    }
    
    .kpi-header {
        font-family: var(--font-mono);
        font-size: var(--font-size-lg);
        font-weight: var(--font-weight-semibold);
        color: var(--text-primary);
        margin-bottom: var(--spacing-md);
        padding-left: 0;
    }
    
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.5rem;
        row-gap: 1rem;
    }
    
    .kpi-item {
        background: transparent;
        border: none;
        border-left: 1px solid rgba(90, 122, 143, 0.35) !important;
        padding: 0.25rem 0.85rem 0.25rem 1.25rem;
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-height: 50px;
        transition: all 0.3s ease;
        position: relative;
    }
    
    .kpi-content-bar {
        position: relative;
        padding-left: 0;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        padding-top: 0;
        height: 100%;
    }
    
    .kpi-item:hover {
        background-color: rgba(90, 122, 143, 0.03);
    }
    
    .kpi-label {
        font-family: var(--font-primary);
        font-size: var(--font-size-sm);
        font-weight: var(--font-weight-medium);
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 2px;
        white-space: nowrap;
    }
    
    .kpi-value-row {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .kpi-value {
        font-family: var(--font-mono);
        font-size: var(--font-size-xl);
        font-weight: var(--font-weight-bold);
        color: #ffffff;
        line-height: 1;
        letter-spacing: -0.02em;
        font-variant-numeric: tabular-nums;
        transition: opacity 0.3s ease-in-out;
    }
    
    .kpi-item:first-child .kpi-value {
        color: #ffffff !important;
        animation: none;
    }
    
    /* Sidebar Styling - Compact & Professional */
    [data-testid="stSidebar"] {
        background-color: var(--sidebar-bg) !important;
        border-right: 1px solid var(--card-border);
        backdrop-filter: blur(10px);
    }
    
    [data-testid="stSidebar"] .block-container {
        padding-top: 3rem; /* Increased top padding matching main */
        padding-left: 1rem;
        padding-right: 1rem;
    }
    
    /* Transparent DataFrames to show Background */
    [data-testid="stDataFrame"] {
        background-color: transparent !important;
    }
    [data-testid="stDataFrame"] div[class*="st"] {
        background-color: transparent !important;
    }
    div[data-testid="stTable"] {
        background-color: transparent !important;
    }
    
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] div, [data-testid="stSidebar"] label {
        font-size: 1rem !important;
    }
    
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        font-family: 'JetBrains Mono', monospace !important;
        color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    /* ============================================= */
    /* SIDEBAR STYLING - ULTRA COMPACT             */
    /* ============================================= */
    
    [data-testid="stSidebar"] {
        background-color: var(--sidebar-bg);
        padding: 1rem 0.75rem;
    }
    
    /* Sidebar Headers - Compact Style */
    [data-testid="stSidebar"] h3 {
        font-family: var(--font-mono) !important;
        font-size: 0.8rem !important;
        font-weight: var(--font-weight-bold) !important;
        color: rgba(148, 163, 184, 0.9) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.08em !important;
        margin-top: 0.75rem !important;
        margin-bottom: 0.5rem !important;
        padding-bottom: 0.25rem !important;
        border-bottom: 1px solid rgba(148, 163, 184, 0.2) !important;
        padding-left: 0 !important;
        background: none !important;
        border-left: none !important;
    }
    
    /* First header no top margin */
    [data-testid="stSidebar"] h3:first-of-type {
        margin-top: 0 !important;
    }
    
    /* Remove section boxes - too bulky */
    [data-testid="stSidebar"] h3 + * {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
        margin-bottom: 0.5rem !important;
    }
    
    /* Compact file uploader */
    [data-testid="stSidebar"] [data-testid="stFileUploader"] {
        background-color: rgba(30, 38, 48, 0.2);
        border: 1px dashed rgba(148, 163, 184, 0.2);
        border-radius: 6px;
        padding: 0.5rem;
        margin-bottom: 0.5rem;
    }
    
    [data-testid="stSidebar"] [data-testid="stFileUploader"]label {
        font-family: var(--font-primary) !important;
        font-size: 0.75rem !important;
        color: var(--text-secondary) !important;
    }
    
    /* Compact buttons */
    [data-testid="stSidebar"] button {
        font-family: var(--font-mono) !important;
        font-size: 0.7rem !important;
        font-weight: var(--font-weight-bold) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
        border-radius: 6px !important;
        padding: 0.4rem 0.6rem !important;
        transition: all 0.2s ease !important;
    }
    
    [data-testid="stSidebar"] button:hover {
        border-color: rgba(75, 125, 163, 0.6) !important;
        background-color: #30363d !important;
        color: #ffffff !important;
        box-shadow: 0 0 6px rgba(75, 125, 163, 0.2);
    }
    
    /* Compact toggles */
    [data-testid="stSidebar"] .stCheckbox {
        margin-bottom: 0.4rem !important;
    }
    
    [data-testid="stSidebar"] .stCheckbox label {
        font-family: var(--font-primary) !important;
        font-size: 0.75rem !important;
        font-weight: var(--font-weight-medium) !important;
        color: var(--text-primary) !important;
    }
    
    /* Compact captions */
    [data-testid="stSidebar"] .stCaption {
        font-family: var(--font-primary) !important;
        font-size: 0.65rem !important;
        color: var(--text-secondary) !important;
        margin-top: 0.25rem !important;
        margin-bottom: 0.5rem !important;
    }
    
    /* Minimal HR spacing */
    [data-testid="stSidebar"] hr {
        margin: 0.75rem 0 !important;
        border-color: rgba(148, 163, 184, 0.1) !important;
    }
    
    /* System status - ultra compact */
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        font-size: 0.7rem !important;
        line-height: 1.3 !important;
        margin-bottom: 0.25rem !important;
    }
    
    /* Expander Styling - Matched to Card Titles */
    .streamlit-expanderHeader {
        background-color: var(--card-bg) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--card-border) !important;
        font-family: var(--font-mono) !important;
        font-size: var(--font-size-lg) !important;
        font-weight: var(--font-weight-semibold) !important;
        text-transform: default !important;
        letter-spacing: 0.05em !important;
        border-radius: var(--radius);
        padding-left: 1rem !important;
        padding-bottom: 0.5rem !important;
        padding-top: 0.5rem !important;
    }
    
    /* Force exact font match for Expander Summaries */
    div[data-testid="stExpander"] details summary p {
         font-family: var(--font-mono) !important;
         font-weight: var(--font-weight-semibold) !important;
         font-size: var(--font-size-lg) !important;
         color: var(--text-primary) !important;
    }
    
    [data-testid="stExpander"] {
        background-color: transparent !important;
        border: none !important;
        margin-bottom: var(--spacing-md) !important;
        padding-top: 0 !important;
    }
    
    /* Expander Content Adjustment */
    [data-testid="stExpanderDetails"] > div {
        padding-bottom: 0.5rem !important;
        padding-top: 0.5rem !important;
    }

    /* Input Fields & Selectboxes */
    .stSelectbox label {
        font-size: var(--font-size-sm) !important;
        color: var(--text-secondary) !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.25rem !important;
    }
    
    .stSelectbox > div > div {
        background-color: var(--card-bg) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: var(--radius);
        font-family: var(--font-mono);
        font-size: var(--font-size-base) !important;
        min-height: 38px;
    }
    
    /* Buttons */
    .stButton>button {
        background-color: #21262d;
        color: #c9d1d9;
        border: 1px solid #30363d;
        border-radius: var(--radius);
        font-family: var(--font-mono);
        font-weight: var(--font-weight-bold);
        font-size: var(--font-size-sm);
        text-transform: uppercase;
        letter-spacing: 0.1em;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        padding: 0.6rem 1rem;
        box-shadow: 0 1px 0 rgba(27,31,36,0.04);
    }
    
    .stButton>button:hover {
        background-color: #30363d;
        border-color: rgba(75, 125, 163, 0.5);
        color: #ffffff;
        transform: translateY(-1px);
        box-shadow: 
            0 0 8px rgba(75, 125, 163, 0.25),
            0 2px 8px rgba(0,0,0,0.2);
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
        border: 1px solid var(--card-border) !important; /* Bluish accent matches corner radius */
        border-radius: 10px;
        background-color: #0d1117 !important;
        overflow: hidden; /* Ensures inner content doesn't bleed past radius */
    }
    
    /* Remove default internal borders to fix "double border" look */
    [data-testid="stDataFrame"] > div {
        border: none !important;
    }
    
    /* Target the internal iframe or container that Streamlit sometimes injects */
    iframe[title="dataframe"] {
        border: none !important;
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
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        border-bottom: 1px solid #21262d !important;
        font-variant-numeric: tabular-nums; /* Aligned numbers */
    }
    
    /* RIGID ALERTS (Terminal Style) */
    [data-testid="stAlert"] {
        background-color: #0d1117 !important;
        border: 1px solid var(--card-border) !important; /* Bluish accent */
        border-left-width: 4px !important;
        border-radius: 4px !important;
        color: var(--text-primary) !important;
    }
    
    [data-testid="stAlert"] [data-testid="stMarkdownContainer"] {
         font-family: 'JetBrains Mono', monospace !important;
         font-size: 0.85rem !important;
    }
    
    /* Chart Containers */
    [data-testid="stPlotlyChart"] {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    

    
    /* Container Borders (st.container(border=True)) */
    /* Container Borders */
    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid rgba(60, 66, 75, 0.5) !important;
        background-color: rgba(13, 17, 23, 0.4) !important; /* Increased Transparency for Nebula */
        backdrop-filter: blur(8px); /* Subtle blur for dashboard cards */
        border-radius: 4px !important;
        padding: 1.25rem !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05) !important;
        margin-bottom: 1.5rem !important;
        transition: transform 0.2s ease, border-color 0.2s ease;
        animation: fadeIn 0.5s ease-out;
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
    
    /* ========================================== */
    /* COMPONENTS                                 */
    /* ========================================== */
    
    /* Card Titles - Unified Styling */
    .card-title {
        font-family: var(--font-mono);
        font-size: var(--font-size-lg);
        font-weight: var(--font-weight-semibold);
        color: var(--text-primary);
        letter-spacing: 0.05em;
        margin-bottom: 0 !important;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        height: 32px;
    }


    
    /* Consistent gap for columns on desktop */
    [data-testid="stHorizontalBlock"] {
        gap: 1.5rem !important;
    }
    
    /* ============================================= */
    /* TAB STYLING - Moonlit Theme                  */
    /* ============================================= */
    
    /* Tab container */
    .stTabs {
        background-color: transparent;
        gap: 0;
    }
    
    /* Tab list container */
    .stTabs [data-baseweb="tab-list"] {
        background-color: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: var(--radius);
        padding: 0.35rem;
        gap: 0.25rem;
    }
    
    /* Individual tabs */
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        color: var(--text-secondary);
        font-family: var(--font-mono);
        font-size: var(--font-size-base);
        font-weight: var(--font-weight-medium);
        padding: 0.5rem 1.25rem;
        transition: all 0.2s ease;
    }
    
    /* Tab hover state */
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(255, 255, 255, 0.03);
        color: var(--text-primary);
    }
    
    /* Active/selected tab */
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: rgba(59, 130, 246, 0.18);
        border: 1px solid rgba(59, 130, 246, 0.6);
        color: var(--text-primary);
       box-shadow: 
            0 0 10px rgba(59, 130, 246, 0.35),
            0 1px 3px rgba(0, 0, 0, 0.2);
    }
    
    /* Remove the default red underline indicator */
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
    
    /* Tab panel content */
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 1.5rem;
    }

    /* ============================================= */
    /* ACCESSIBILITY ENHANCEMENTS */
    /* ============================================= */
    
    /* High-Contrast Focus Indicators */
    button:focus-visible,
    [data-baseweb="select"]:focus-within,
    .stButton>button:focus-visible {
        outline: 2px solid #60A5FA !important;
        outline-offset: 2px;
        box-shadow: 0 0 0 4px rgba(96, 165, 250, 0.2) !important;
    }
    
    /* Remove default outline */
    *:focus {
        outline: none;
    }
    
    *:focus-visible {
        outline: 2px solid #60A5FA;
        outline-offset: 2px;
    }
    
    /* ============================================= */
    /* LOADING STATES & ANIMATIONS */
    /* ============================================= */
    
    /* Skeleton Loading Animation */
    @keyframes shimmer {
        0% {
            background-position: -1000px 0;
        }
        100% {
            background-position: 1000px 0;
        }
    }
    
    .skeleton {
        background: linear-gradient(
            90deg,
            rgba(255, 255, 255, 0.03) 0%,
            rgba(255, 255, 255, 0.08) 50%,
            rgba(255, 255, 255, 0.03) 100%
        );
        background-size: 1000px 100%;
        animation: shimmer 2s infinite;
        border-radius: 10px;
    }
    
    .skeleton-kpi {
        height: 85px;
        width: 100%;
        margin-bottom: 1px;
    }
    
    .skeleton-chart {
        height: 520px;
        width: 100%;
    }
    
    /* Fade-in animation for components */
    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
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
            gap: 1rem;
        }
    }
    
    /* Wide Desktop (Compact Single Row for KPIs) */
    @media only screen and (min-width: 1400px) {
        .kpi-grid-6 {
            grid-template-columns: repeat(6, 1fr) !important; /* All 6 in one row */
        }
        .kpi-grid-9 {
            grid-template-columns: repeat(5, 1fr) !important; /* 5 top, 4 bottom - very compact */
        }
        .kpi-grid {
             gap: 1.25rem; /* Tighter gap for wide screens */
        }
    }
    
    /* Standard Desktop / Laptop */
    @media only screen and (min-width: 769px) {
        .kpi-grid {
            /* Fallback used for intermediate widths or if class is generic */
            gap: 1.5rem;
        }
        
        /* Default for standard desktop if not overridden by Wide query above */
        .kpi-grid-6 {
            grid-template-columns: repeat(3, 1fr);
        }
        .kpi-grid-9 {
            grid-template-columns: repeat(3, 1fr);
        }
    }
    
    /* Mobile (Max Width: 768px) */
    @media only screen and (max-width: 768px) {
        
        /* 1. FORCE COLUMN STACKING - Remove all column spacing */
        [data-testid="column"] {
            width: 100% !important;
            flex: 1 1 auto !important;
            min-width: 100% !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }
        
        /* Set gap on horizontal blocks to match vertical spacing on mobile */
        [data-testid="stHorizontalBlock"] {
            gap: 2.5rem !important;
        }

        /* 2. MOBILE KPI GRID - 2 Columns */
        .kpi-grid {
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 0.8rem;
        }
        
        /* Mobile KPI borders - inherit from desktop, works naturally */
        .kpi-item {
            min-height: 50px;
            padding: 0.65rem 0.75rem 0.65rem 1rem !important;
        }
        
        /* Adjust gradient separator for mobile */
        .kpi-content-bar {
             padding-left: 14px;
        }
        
        .kpi-content-bar::before {
            width: 2.5px; /* Slightly thinner on mobile */
        }
        
        /* Slightly smaller fonts for mobile KPI to fit delta */
        .kpi-value {
            font-size: 1.1rem !important; 
        }
        .kpi-label {
            font-size: 0.65rem !important; 
        }
        .metric-delta {
            font-size: 0.65rem !important;
            margin-left: 4px !important;
        }
        
        /* MOBILE: Compact KPI Board with consistent spacing */
        .kpi-board {
            padding: 1rem !important;
            margin-bottom: 2.5rem !important; /* Match desktop exactly */
        }
        
        /* 3. COMPACT CHART TILE SPACING - Consistent at 2.5rem */
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.75rem !important;
            margin-bottom: 2.5rem !important; /* Match KPI board exactly */
        }
        .card-title {
            margin-bottom: 0.5rem !important;
            font-size: 1rem; /* Slightly smaller on mobile */
        }
        
        /* 4. TYPOGRAPHY */
        .main-header { font-size: 1.4rem; }
        .sub-header { font-size: 0.7rem; margin-bottom: 1.5rem; }
        .kpi-value { font-size: 1.0rem; }
        .kpi-label { font-size: 0.7rem; }
        .metric-label { font-size: 0.7rem; }
        
        /* 5. MOBILE CHART ADJUSTMENTS */
        [data-testid="stPlotlyChart"] {
            max-height: 400px !important;
        }
        
        /* Aggressive margin reduction for charts */
        [data-testid="stPlotlyChart"] > div {
            margin-bottom: 0 !important;
        }
        
        /* MOBILE: Expander spacing to match containers */
        [data-testid="stExpander"] {
            margin-bottom: 1.5rem !important;
        }
        
        /* MOBILE: Reduce container padding to minimize wasted space */
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.5rem !important;
        }
        
        /* MOBILE: Tighter card titles */
        .card-title {
            margin-bottom: 0.25rem !important;
            font-size: var(--font-size-md) !important;
        }
        

    }
    
    /* ============================================= */
    /* CHART RESPONSIVE HEIGHTS (Simplified)        */
    /* ============================================= */

    /* Chart Heights */
    @media only screen and (max-width: 768px) {
        /* Just ensure containers don't expand beyond chart */
        [data-testid="stVerticalBlockBorderWrapper"] {
            padding: 0.75rem !important;
        }
        
        /* Hide modebar on mobile */
        .modebar {
            display: none !important;
        }
        
        /* Increase gap between stacked columns on mobile */
        [data-testid="stHorizontalBlock"] {
            gap: 2.5rem !important;
        }
    }
    
    /* Desktop column spacing */
    @media only screen and (min-width: 769px) {
        [data-testid="stHorizontalBlock"] {
            gap: 1.5rem !important;
        }
    }
    
</style>
"""
