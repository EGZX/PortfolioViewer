"""Visualization components using Plotly for interactive charts."""

from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


def create_allocation_donut(
    holdings_df: pd.DataFrame, 
    min_pct: float = 2.0, 
    title: str = "Portfolio Allocation",
    privacy_mode: bool = False,
    compact_mode: bool = False  # NEW: Explicit mobile signal
) -> go.Figure:
    """
    Create an interactive donut chart showing portfolio allocation.
    Optimized for futuristic look and cleaner legend.
    
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
    if 'Name' in holdings_df.columns:
        holdings_df['Display_Label'] = holdings_df.apply(
            lambda row: row['Name'] if row['Name'] and row['Name'] != row['Ticker'] else row['Ticker'],
            axis=1
        )
    else:
        holdings_df['Display_Label'] = holdings_df['Ticker']
    
    # Sort by value descending
    holdings_df = holdings_df.sort_values(market_value_col, ascending=False)
    
    # Logic: Take Top 9, Group rest as "Others"
    # This ensures the legend never overflows screen space
    top_n = 9
    
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
        
    # Telemetry / Aerospace Palette (High Contrast, Technical)
    colors = [
        '#0ea5e9', # Sky Blue (Primary)
        '#6366f1', # Indigo (Secondary)
        '#22c55e', # Signal Green
        '#eab308', # Amber (Warning)
        '#ec4899', # Pink (Highlight)
        '#8b5cf6', # Violet
        '#f97316', # Orange
        '#14b8a6', # Teal
        '#64748b', # Slate
        '#334155', # Dark Slate (Others)
    ]

    # Privacy masking for hover
    val_fmt = "€%{value:,.2f}" if not privacy_mode else "••••••"

    fig = go.Figure(data=[go.Pie(
        labels=display_df['Display_Label'],
        values=display_df[market_value_col],
        hole=0.75, # Thinner ring
        hovertemplate='<b>%{label}</b><br>' +
                     f'{val_fmt}<br>' +
                     '%{percent}<br>' +
                     '<extra></extra>',
        textinfo='none',  # Clean look, no text on chart
        marker=dict(
            colors=colors,
            line=dict(color='#0e1117', width=3) # Match dark background
        )
    )])
    
    # Center text showing total or top item? 
    # Let's keep it clean for now.
    
    # Layout Logic: Use compact_mode parameter instead of title check
    if compact_mode:
        # Mobile: compact sizing
        title_dict = dict(text="") if not title else dict(text=title, x=0, font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 40
        margin_b = 50  # Mobile: space for legend
        chart_height = 450  # Mobile: balanced height (fits legend without being too tall)
    else:
        # Desktop: full sizing
        title_dict = dict(text="") if not title else dict(text=title, x=0, font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 40
        margin_b = 120  # Desktop: space for legend
        chart_height = 580  # Desktop: full size

    fig.update_layout(
        title=title_dict,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15, 
            xanchor="center",
            x=0.5,
            font=dict(color='#9CA3AF', size=11, family="Inter"),
            bgcolor='rgba(0,0,0,0)',
        ),
        height=chart_height,
        margin=dict(t=margin_t, b=margin_b, l=20, r=20), 
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color="#9CA3AF")
    )
    
    return fig


def create_performance_chart(
    dates: List[str],
    net_deposits: List[float],
    portfolio_values: List[float],
    cost_basis_values: List[float] = None,
    title: Optional[str] = "Performance History",
    privacy_mode: bool = False,
    compact_mode: bool = False  # NEW: Explicit mobile signal
) -> go.Figure:
    """
    Create a modern area chart for portfolio performance.
    Includes native Range Selector to replace external UI elements.
    
    Args:
        compact_mode: If True, generates a compact chart for mobile (smaller height, tighter margins)
    """
    if not dates or not net_deposits or not portfolio_values:
        return go.Figure()
    
    fig = go.Figure()
    
    # Privacy masking
    val_fmt = "€%{y:,.0f}" if not privacy_mode else "••••••"
    
    # 1. Net Deposits (Base Line)
    fig.add_trace(go.Scatter(
        x=dates,
        y=net_deposits,
        name='Net Deposits',
        mode='lines',
        line=dict(color='#64748b', width=2, dash='dot'),
        hovertemplate=f'<b>Deposits</b>: {val_fmt}<extra></extra>'
    ))
    
    # 2. Cost Basis (Optional)
    if cost_basis_values:
        fig.add_trace(go.Scatter(
            x=dates,
            y=cost_basis_values,
            name='Cost Basis',
            mode='lines',
            line=dict(color='#94a3b8', width=1.5), 
            hovertemplate=f'<b>Cost</b>: {val_fmt}<extra></extra>'
        ))
    
    # 3. Net Worth (Gradient Area)
    fig.add_trace(go.Scatter(
        x=dates,
        y=portfolio_values,
        name='Net Worth',
        mode='lines',
        line=dict(color='#3b82f6', width=3),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.05)', # Ultra-subtle fill
        hovertemplate=f'<b>Net Worth</b>: {val_fmt}<extra></extra>'
    ))
    
    # Layout Logic: Use compact_mode parameter instead of title check
    if compact_mode:
        # Mobile: compact sizing
        title_dict = dict(text="") if not title else dict(text=title, x=0, font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 60
        margin_b = 30  # Mobile: compact bottom margin
        chart_height = 420  # Mobile: compact height
    else:
        # Desktop: full sizing
        title_dict = dict(text="") if not title else dict(text=title, x=0, font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 60
        margin_b = 80  # Desktop: space for legend
        chart_height = 580  # Desktop: full size
    
    fig.update_layout(
        title=title_dict,
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
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
                bgcolor='rgba(20, 20, 20, 0.8)', # Darker, more solid background
                activecolor='#3b82f6',
                font=dict(color='#FFFFFF', size=11, weight=700), # Bright white text
                y=1.12, # Moved up to avoid hover collision
                x=1,
                xanchor='right'
            )
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            zeroline=False,
            tickformat='s',
            tickfont=dict(color='#9CA3AF'),
            showticklabels=not privacy_mode 
        ),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='top',
            y=-0.2,
            xanchor='center',
            x=0.5,
            font=dict(color='#E5E7EB', size=12),
            bgcolor='rgba(0,0,0,0)',
            itemsizing='constant',
            entrywidth=120,
        ),
        height=chart_height,
        margin=dict(t=margin_t + 30, b=margin_b + 30, l=30, r=20), # Increased top margin for selector
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
