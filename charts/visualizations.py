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
    
    Args:
        holdings_df: DataFrame with columns ['Ticker', 'Name', 'Market Value']
        min_pct: Minimum percentage to show separately (default: 2%)
    
    Returns:
        Plotly Figure object
    """
    if holdings_df.empty:
        logger.warning("No holdings data for allocation chart")
        return go.Figure()
    
    # Calculate total value
    total_value = holdings_df['Market Value'].sum()
    
    if total_value <= 0:
        logger.warning("Total portfolio value is zero")
        return go.Figure()
    
    # Calculate percentages
    holdings_df = holdings_df.copy()
    holdings_df['Percentage'] = (holdings_df['Market Value'] / total_value) * 100
    
    # Use Name for display, fallback to Ticker if Name is missing
    if 'Name' in holdings_df.columns:
        holdings_df['Display_Label'] = holdings_df.apply(
            lambda row: row['Name'] if row['Name'] and row['Name'] != row['Ticker'] else row['Ticker'],
            axis=1
        )
    else:
        holdings_df['Display_Label'] = holdings_df['Ticker']
    
    # Group small holdings into "Other"
    large_holdings = holdings_df[holdings_df['Percentage'] >= min_pct].copy()
    small_holdings = holdings_df[holdings_df['Percentage'] < min_pct]
    
    if not small_holdings.empty:
        other_row = pd.DataFrame([{
            'Display_Label': 'Other',
            'Market Value': small_holdings['Market Value'].sum(),
            'Percentage': small_holdings['Percentage'].sum()
        }])
        display_df = pd.concat([large_holdings, other_row], ignore_index=True)
    else:
        display_df = large_holdings
    
    # Sort by value
    display_df = display_df.sort_values('Market Value', ascending=False)
    
    # Create donut chart
    fig = go.Figure(data=[go.Pie(
        labels=display_df['Display_Label'],
        values=display_df['Market Value'],
        hole=0.4,
        hovertemplate='<b>%{label}</b><br>' +
                     'Value: €%{value:,.2f}<br>' +
                     'Percentage: %{percent}<br>' +
                     '<extra></extra>',
        textinfo='percent',
        textposition='auto',
        marker=dict(
            colors=px.colors.qualitative.Set3,
            line=dict(color='white', width=2)
        )
    )])
    
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.05,
            xanchor="center",
            x=0.5
        ),
        height=500,
        margin=dict(t=30, b=150, l=20, r=20)
    )
    
    logger.info(f"Created allocation chart with {len(display_df)} segments")
    
    return fig


def create_performance_chart(
    dates: List[str],
    net_deposits: List[float],
    portfolio_values: List[float],
    cost_basis_values: List[float] = None
) -> go.Figure:
    """
    Create an area chart showing net deposits vs portfolio value over time.
    
    Args:
        dates: List of dates (as strings)
        net_deposits: Net deposits (deposits - withdrawals) at each date
        portfolio_values: Portfolio net worth (holdings + cash) at each date
        cost_basis_values: Cost basis of holdings at each date (optional)
    
    Returns:
        Plotly Figure object
    """
    if not dates or not net_deposits or not portfolio_values:
        logger.warning("No data for performance chart")
        return go.Figure()
    
    fig = go.Figure()
    
    # Net Deposits (what you've put in)
    fig.add_trace(go.Scatter(
        x=dates,
        y=net_deposits,
        name='Net Deposits',
        mode='lines',
        line=dict(color='#636EFA', width=2, dash='dot'),
        hovertemplate='<b>Net Deposits</b><br>' +
                     'Date: %{x}<br>' +
                     'Amount: €%{y:,.2f}<br>' +
                     '<extra></extra>'
    ))
    
    # Cost Basis (what your holdings cost)
    if cost_basis_values:
        fig.add_trace(go.Scatter(
            x=dates,
            y=cost_basis_values,
            name='Cost Basis',
            mode='lines',
            line=dict(color='#FFA15A', width=2, dash='dash'),
            hovertemplate='<b>Cost Basis</b><br>' +
                         'Date: %{x}<br>' +
                         'Amount: €%{y:,.2f}<br>' +
                         '<extra></extra>'
        ))
    
    # Net Worth (what you have)
    fig.add_trace(go.Scatter(
        x=dates,
        y=portfolio_values,
        name='Net Worth',
        mode='lines',
        line=dict(color='#00CC96', width=3),
        fill='tozeroy',
        fillcolor='rgba(0, 204, 150, 0.1)',
        hovertemplate='<b>Net Worth</b><br>' +
                     'Date: %{x}<br>' +
                     'Value: €%{y:,.2f}<br>' +
                     '<extra></extra>'
    ))
    
    fig.update_layout(
        title={
            'text': 'Portfolio Performance Over Time',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'color': '#333'}
        },
        xaxis=dict(
            title='Date',
            showgrid=True,
            gridcolor='#E5E5E5',
            rangeslider=dict(visible=False)
        ),
        yaxis=dict(
            title='Value (€)',
            showgrid=True,
            gridcolor='#E5E5E5',
            tickformat=',.0f'
        ),
        hovermode='x unified',
        legend=dict(
            orientation='h',
            yanchor='bottom',
            y=1.02,
            xanchor='center',
            x=0.5
        ),
        height=500,
        margin=dict(t=80, b=60, l=80, r=40),
        plot_bgcolor='white'
    )
    
    logger.info(f"Created performance chart with {len(dates)} data points")
    
    return fig



def create_simple_bar_chart(data: Dict[str, float], title: str) -> go.Figure:
    """
    Create a simple bar chart (alternative visualization).
    
    Args:
        data: Dictionary mapping labels to values
        title: Chart title
    
    Returns:
        Plotly Figure object
    """
    fig = go.Figure(data=[
        go.Bar(
            x=list(data.keys()),
            y=list(data.values()),
            marker_color='#636EFA',
            hovertemplate='<b>%{x}</b><br>Value: €%{y:,.2f}<extra></extra>'
        )
    ])
    
    fig.update_layout(
        title={
            'text': title,
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title='',
        yaxis_title='Value (€)',
        yaxis=dict(tickformat=',.0f'),
        height=400,
        margin=dict(t=60, b=40, l=80, r=40)
    )
    
    return fig
