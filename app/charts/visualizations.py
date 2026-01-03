"""Visualization components using Plotly for interactive charts."""

from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.express as px 
import pandas as pd

from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)

# ========================================
# CHART STYLING CONSTANTS
# ========================================

# Chart Dimensions
DESKTOP_HEIGHT = 520
MOBILE_HEIGHT = 320

# Shared Typography
CHART_TITLE_FONT = dict(size=18, family="JetBrains Mono", color="#e6e6e6")
CHART_LEGEND_FONT = dict(color='#E5E7EB', family="Inter")

# Hover Label Styling
CHART_HOVER_LABEL = dict(
    bgcolor='rgba(17, 24, 39, 0.95)',
    bordercolor='#4B7DA3',
    font_size=13,
    font_family='JetBrains Mono'
)

# Shared Moonlit Palette
MOONLIT_COLORS = [
    'rgba(30, 58, 138, 0.65)',   # Deep Blue
    'rgba(124, 58, 237, 0.65)',  # Purple
    'rgba(16, 185, 129, 0.65)',  # Emerald
    'rgba(245, 158, 11, 0.60)',  # Amber/Orange
    'rgba(236, 72, 153, 0.65)',  # Pink
    'rgba(14, 165, 233, 0.65)',  # Sky Blue
    'rgba(168, 85, 247, 0.65)',  # Violet
    'rgba(34, 197, 94, 0.65)',   # Green
    'rgba(251, 146, 60, 0.60)',  # Orange
    'rgba(20, 184, 166, 0.65)',  # Teal
    'rgba(139, 92, 246, 0.65)',  # Indigo
    'rgba(52, 211, 153, 0.65)',  # Emerald Light
    'rgba(248, 113, 113, 0.60)', # Red
    'rgba(96, 165, 250, 0.65)',  # Blue Light
    'rgba(167, 139, 250, 0.65)', # Purple Light
]

def create_allocation_donut(
    holdings_df: pd.DataFrame, 
    min_pct: float = 2.0, 
    title: str = "Portfolio Allocation",
    privacy_mode: bool = False,
    compact_mode: bool = False
) -> go.Figure:
    """
    Create an interactive donut chart showing portfolio allocation.
    
    Args:
        compact_mode: If True, generates a compact chart for mobile (smaller height, tighter margins)
    """
    if holdings_df.empty:
        return go.Figure()
    
    # Calculate total value
    market_value_col = 'Market Value (EUR)' if 'Market Value (EUR)' in holdings_df.columns else 'Market Value'
    total_value = holdings_df[market_value_col].sum()
    
    if total_value <= 0:
        return go.Figure()
    
    # Calculate percentages
    holdings_df = holdings_df.copy()
    holdings_df['Percentage'] = (holdings_df[market_value_col] / total_value) * 100
    
    # Use Name for display
    if 'Label' in holdings_df.columns:
        holdings_df['Display_Label'] = holdings_df['Label']
    elif 'Name' in holdings_df.columns:
        holdings_df['Display_Label'] = holdings_df.apply(
            lambda row: row['Name'] if row['Name'] and row['Name'] != row['Ticker'] else row['Ticker'],
            axis=1
        )
    else:
        holdings_df['Display_Label'] = holdings_df['Ticker']
    
    # Sort by value descending
    holdings_df = holdings_df.sort_values(market_value_col, ascending=False)
    
    # Take Top 15
    top_n = 15
    
    if len(holdings_df) > top_n:
        large_holdings = holdings_df.iloc[:top_n].copy()
        small_holdings = holdings_df.iloc[top_n:]
        
        if not small_holdings.empty:
            other_val = small_holdings[market_value_col].sum()
            other_pct = small_holdings['Percentage'].sum()
            
            other_row = pd.DataFrame([{
                'Display_Label': 'Others',
                'Ticker': 'OTHERS',
                market_value_col: other_val,
                'Percentage': other_pct
            }])
            display_df = pd.concat([large_holdings, other_row], ignore_index=True)
        else:
            display_df = large_holdings
    else:
        display_df = holdings_df
        
    # Use Shared Palette
    colors = MOONLIT_COLORS

    # Privacy masking for hover
    val_fmt = "€%{value:,.2f}" if not privacy_mode else "••••••"

    fig = go.Figure(data=[go.Pie(
        labels=display_df['Display_Label'],
        values=display_df[market_value_col],
        hole=0.60,
        hovertemplate='<b>%{label}</b><br>' +
                     f'{val_fmt}<br>' +
                     '%{percent}<br>' +
                     '<extra></extra>',
        hoverlabel=CHART_HOVER_LABEL,
        textinfo='none',
        marker=dict(
            colors=colors,
            line=dict(color='#0e1117', width=2)
        )
    )])
    
    # Layout Logic
    title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
    
    # Chart Height
    final_height = MOBILE_HEIGHT if compact_mode else DESKTOP_HEIGHT
    
    # Legend Logic: 
    # Desktop: Hide (Immersive)
    # Mobile: Show (Touch accessibility)
    show_legend_bool = True if compact_mode else False

    if compact_mode:
        margin_t = 0 if not title else 40
        margin_b = 0
        margin_l = 20
        margin_r = 20
        legend_y = -0.05
    else:
        # Desktop
        margin_t = 0 if not title else 60
        margin_b = 40
        margin_l = 40
        margin_r = 40
        legend_y = -0.1

    fig.update_layout(
        title=title_dict,
        showlegend=show_legend_bool, 
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.05 if compact_mode else legend_y,
            xanchor="center",
            x=0.5,
            font=dict(**CHART_LEGEND_FONT, size=9 if compact_mode else 11),
            itemwidth=50 if compact_mode else 70,
            bgcolor='rgba(0,0,0,0)',
        ),
        height=final_height, 
        margin=dict(t=margin_t, b=0 if compact_mode else margin_b, l=margin_l, r=margin_r), 
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color="#9CA3AF"),
        annotations=[dict(text=f"{total_value:,.0f} €", x=0.5, y=0.5, font_size=22, showarrow=False, font=dict(family="JetBrains Mono", color="white", weight=700))] if total_value > 0 else []
    )
    
    fig.update_traces(hole=0.60, hoverinfo="label+percent+value")
    
    return fig


def create_allocation_treemap(
    holdings_df: pd.DataFrame, 
    title: str = "Portfolio Allocation",
    privacy_mode: bool = False,
    compact_mode: bool = False
) -> go.Figure:
    """
    Create a modern TreeMap chart for asset allocation.
    Flat structure with Moonlit aesthetic.
    """
    if holdings_df.empty:
        return go.Figure()
    
    market_value_col = 'Market Value (EUR)' if 'Market Value (EUR)' in holdings_df.columns else 'Market Value'
    
    # Ensure Asset Type exists, default to 'Assets' if missing
    if 'Asset Type' not in holdings_df.columns:
        holdings_df['Asset Type'] = 'Assets'
        
    # Calculate % for labels
    total_val = holdings_df[market_value_col].sum()
    holdings_df['Percentage'] = (holdings_df[market_value_col] / total_val) * 100
    
    # Label Logic: Ticker + %
    if 'Label' not in holdings_df.columns:
        holdings_df['Label'] = holdings_df['Ticker']
    
    # Use Shared Palette
    colors = MOONLIT_COLORS
    
    # Use plotly.express (px) for Treemap generation
    # Path "Portfolio" -> "Label" (Ticker)
    fig = px.treemap(
        holdings_df, 
        path=['Label'], 
        values=market_value_col,
        color='Label', 
        color_discrete_sequence=colors,
        hover_data={'Name': True, market_value_col: True, 'Percentage': ':.1f'}
    )
    
    # Custom Hover Template
    val_fmt = "€%{value:,.0f}" if not privacy_mode else "••••••"
    
    # Use customdata to access 'Name' (stored in hover_data)
    # px automatically puts hover_data into customdata.
    # Index 0 = Name (based on hover_data dict order usually)
    fig.update_traces(
        hovertemplate='<b>%{label}</b><br>' +
                      f'Value: {val_fmt}<br>' +
                      'Share: %{percentRoot:.1%}<br>' +
                      '<extra></extra>',
        marker=dict(
            line=dict(width=1, color='rgba(148, 163, 184, 0.2)'), # Subtle slate border
            cornerradius=0 # Sharp edges for clean grid
        ),
        texttemplate='%{label}<br>%{percentRoot:.1%}',  # Format with 1 decimal
        textfont=dict(family="JetBrains Mono", size=14, color="#e2e8f0"), # Light text
        textposition="middle center",
        root_color="rgba(0,0,0,0)" # Transparent root
    )
    
    # Chart Height
    final_height = MOBILE_HEIGHT if compact_mode else DESKTOP_HEIGHT
    
    # Margins - Zeroed out to fill container
    margin_t = 0 if not title else 30
    margin_b = 0
    margin_l = 0
    margin_r = 0
        
    title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))

    fig.update_layout(
        title=title_dict,
        height=final_height,
        margin=dict(t=margin_t, b=margin_b, l=margin_l, r=margin_r),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color="#9CA3AF"),
        uniformtext=dict(minsize=10, mode='hide') # Hide labels if too small
    )

    return fig


def create_performance_chart(
    dates: List[str],
    net_deposits: List[float],
    portfolio_values: List[float],
    cost_basis_values: List[float] = None,
    title: Optional[str] = "Performance History",
    privacy_mode: bool = False,
    compact_mode: bool = False
) -> go.Figure:
    """
    Create chart area for portfolio performance.
    Includes native Range Selector.
    
    Args:
        compact_mode: If True, generates a compact chart for mobile (smaller height, tighter margins)
    """
    if not dates or not net_deposits or not portfolio_values:
        return go.Figure()
    
    fig = go.Figure()
    
    # Privacy masking
    val_fmt = "€%{y:,.0f}" if not privacy_mode else "••••••"
    
    # 1. Net Deposits
    fig.add_trace(go.Scatter(
        x=dates,
        y=net_deposits,
        name='Net Deposits',
        mode='lines',
        line=dict(color='#64748b', width=2, dash='dot'),
        hovertemplate=f'<b>Deposits</b>: {val_fmt}<extra></extra>',
        hoverlabel=CHART_HOVER_LABEL
    ))
    
    # 2. Cost Basis
    if cost_basis_values:
        fig.add_trace(go.Scatter(
            x=dates,
            y=cost_basis_values,
            name='Cost Basis',
            mode='lines',
            line=dict(color='#f59e0b', width=1.5), 
            hovertemplate=f'<b>Cost</b>: {val_fmt}<extra></extra>',
            hoverlabel=CHART_HOVER_LABEL
        ))
    
    # 3. Net Worth
    fig.add_trace(go.Scatter(
        x=dates,
        y=portfolio_values,
        name='Net Worth',
        mode='lines',
        line=dict(color='#3b82f6', width=2.5),
        fill='tozeroy', 
        fillcolor='rgba(59, 130, 246, 0.12)',
        hovertemplate=f'<b>Net Worth</b>: {val_fmt}<extra></extra>',
        hoverlabel=CHART_HOVER_LABEL
    ))
    
    # Layout Configuration
    if compact_mode:
        title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(size=14, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 40
        margin_b = 0
        chart_height = MOBILE_HEIGHT
    else:
        title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(**CHART_TITLE_FONT))
        margin_t = 0 if not title else 60
        margin_b = 80
        chart_height = DESKTOP_HEIGHT
    
    fig.update_layout(
        title=title_dict,
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.08)',
            gridwidth=1,
            griddash='dot',
            zeroline=False,
            showline=True,
            linecolor='#374151',
            tickfont=dict(color='#9CA3AF'),
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="ALL")
                ]),
                bgcolor='rgba(20, 20, 20, 0.9)', 
                activecolor='#3b82f6',
                bordercolor='#30363d',
                borderwidth=1,
                font=dict(color='#FFFFFF', size=13, weight=700),
                y=-0.12 if not compact_mode else -0.25,
                x=1,
                xanchor='right',
                yanchor='top'
            )
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.08)',
            gridwidth=1,
            griddash='dot',
            zeroline=False,
            tickformat='s',
            tickfont=dict(color='#9CA3AF'),
            showticklabels=not privacy_mode 
        ),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            # Move legend further down if we ever show it, to avoid collision
            y=1.00 if not compact_mode else -0.50,
            xanchor='center',
            x=0.5,
            font=dict(**CHART_LEGEND_FONT, size=9 if compact_mode else 12),
            bgcolor='rgba(0,0,0,0)',
            itemsizing='constant',
            entrywidth=80 if compact_mode else 90,
        ),
        showlegend=not compact_mode,
        height=chart_height,
        # Increase bottom margin significantly for mobile to fit selector
        margin=dict(t=30 if compact_mode else 60, b=110 if compact_mode else 50, l=0, r=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="JetBrains Mono", size=11)
    )
    
    return fig


def create_simple_bar_chart(data: Dict[str, float], title: str) -> go.Figure:
    """
    Create a simple bar chart (alternative visualization).
    """
    fig = go.Figure(data=[
        go.Bar(
            x=list(data.keys()),
            y=list(data.values()),
            marker_color='#3b82f6',
            marker=dict(line=dict(color='#60A5FA', width=1)),
            hovertemplate='<b>%{x}</b><br>€%{y:,.2f}<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title={
            'text': title,
            'x': 0,
            'font': {'size': 14, 'color': '#E5E7EB'}
        },
        xaxis=dict(
            tickfont=dict(color='#9CA3AF'),
            showgrid=False
        ),
        yaxis=dict(
            gridcolor='rgba(255,255,255,0.05)',
            tickfont=dict(color='#9CA3AF')
        ),
        height=300,
        margin=dict(t=40, b=20, l=40, r=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter")
    )
    
    return fig
