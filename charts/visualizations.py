"""Visualization components using Plotly for interactive charts."""

from typing import Dict, List, Optional
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


def create_allocation_donut(holdings_df: pd.DataFrame, min_pct: float = 2.0) -> go.Figure:
    """
    Create an interactive donut chart showing portfolio allocation.
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
    
    # Use Name for display, fallback to Ticker if Name is missing
    if 'Name' in holdings_df.columns:
        holdings_df['Display_Label'] = holdings_df.apply(
            lambda row: row['Name'] if row['Name'] and row['Name'] != row['Ticker'] else row['Ticker'],
            axis=1
        )
    else:
        holdings_df['Display_Label'] = holdings_df['Ticker']
    
    # Group small holdings
    large_holdings = holdings_df[holdings_df['Percentage'] >= min_pct].copy()
    small_holdings = holdings_df[holdings_df['Percentage'] < min_pct]
    
    if not small_holdings.empty:
        other_row = pd.DataFrame([{
            'Display_Label': 'Others',
            market_value_col: small_holdings[market_value_col].sum(),
            'Percentage': small_holdings['Percentage'].sum()
        }])
        display_df = pd.concat([large_holdings, other_row], ignore_index=True)
    else:
        display_df = large_holdings
    
    # Sort
    display_df = display_df.sort_values(market_value_col, ascending=False)
    
    # Custom Cyber Palette
    cyber_colors = [
        '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', 
        '#6366f1', '#ec4899', '#14b8a6', '#f97316', '#64748b'
    ]

    fig = go.Figure(data=[go.Pie(
        labels=display_df['Display_Label'],
        values=display_df[market_value_col],
        hole=0.6,
        hovertemplate='<b>%{label}</b><br>' +
                     '€%{value:,.2f}<br>' +
                     '%{percent}<br>' +
                     '<extra></extra>',
        textinfo='percent',  # Only show percent on chart to avoid clutter/cutoff
        textposition='outside',
        marker=dict(
            colors=cyber_colors,
            line=dict(color='#1e2329', width=2)
        )
    )])
    
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="center",
            x=0.5,
            font=dict(color='#9CA3AF', size=12)
        ),
        height=600,
        margin=dict(t=30, b=150, l=20, r=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color="#9CA3AF")
    )
    
    return fig


def create_performance_chart(
    dates: List[str],
    net_deposits: List[float],
    portfolio_values: List[float],
    cost_basis_values: List[float] = None
) -> go.Figure:
    """
    Create a modern area chart for portfolio performance.
    """
    if not dates or not net_deposits or not portfolio_values:
        return go.Figure()
    
    fig = go.Figure()
    
    # 1. Net Deposits (Base Line)
    fig.add_trace(go.Scatter(
        x=dates,
        y=net_deposits,
        name='Net Deposits',
        mode='lines',
        line=dict(color='#64748b', width=2, dash='dot'),
        hovertemplate='<b>Deposits</b>: €%{y:,.0f}<extra></extra>'
    ))
    
    # 2. Cost Basis (Optional)
    if cost_basis_values:
        fig.add_trace(go.Scatter(
            x=dates,
            y=cost_basis_values,
            name='Cost Basis',
            mode='lines',
            line=dict(color='#94a3b8', width=1.5), # Made slightly thicker
            # visible='legendonly', # REMOVED: Show by default
            hovertemplate='<b>Cost</b>: €%{y:,.0f}<extra></extra>'
        ))
    
    # 3. Net Worth (Gradient Area)
    fig.add_trace(go.Scatter(
        x=dates,
        y=portfolio_values,
        name='Net Worth',
        mode='lines',
        line=dict(color='#3b82f6', width=3),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.1)',
        hovertemplate='<b>Net Worth</b>: €%{y:,.0f}<extra></extra>'
    ))
    
    fig.update_layout(
        title='', # Explicit empty string to fix "undefined"
        xaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            zeroline=False,
            showline=True,
            linecolor='#374151',
            tickfont=dict(color='#9CA3AF')
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='rgba(255,255,255,0.05)',
            zeroline=False,
            tickformat='s',
            tickfont=dict(color='#9CA3AF')
        ),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='left',
            x=0,
            font=dict(color='#E5E7EB'),
            bgcolor='rgba(0,0,0,0)'
        ),
        height=500,
        margin=dict(t=40, b=60, l=30, r=20),
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
