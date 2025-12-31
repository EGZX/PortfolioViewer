"""Visualization components using Plotly for interactive charts."""

from typing import Dict, List, Optional
import plotly.graph_objects as go
import pandas as pd

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


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
    if 'Name' in holdings_df.columns:
        holdings_df['Display_Label'] = holdings_df.apply(
            lambda row: row['Name'] if row['Name'] and row['Name'] != row['Ticker'] else row['Ticker'],
            axis=1
        )
    else:
        holdings_df['Display_Label'] = holdings_df['Ticker']
    
    # Sort by value descending
    holdings_df = holdings_df.sort_values(market_value_col, ascending=False)
    
    # Logic: Take Top 15 (Utilize full space without legend)
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
        
    # High Contrast / Neon Palette
    colors = [
        '#00e5ff', # Cyan 
        '#ffffff', # White
        '#d500f9', # Neon Purple
        '#ff1744', # Neon Red/Pink
        '#00e676', # Neon Green
        '#ffea00', # Neon Yellow
        '#2979ff', # Blue
        '#ff9100', # Orange
        '#76ff03', # Lime
        '#f50057', # Pink
        '#3d5afe', # Indigo
        '#1de9b6', # Teal
        '#ffc400', # Amber
        '#90a4ae', # Blue Grey
        '#546e7a'  # Dark Slate
    ]

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
        hoverlabel=dict(font_size=16, font_family="JetBrains Mono"),
        textinfo='none',
        marker=dict(
            colors=colors,
            line=dict(color='#0e1117', width=2)
        )
    )])
    
    # Layout Logic
    title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
    
    # Universal Layout (Desktop & Mobile)
    final_height = 450 if compact_mode else 520
    
    # Legend Logic: 
    # Desktop: Hide (Immersive)
    # Mobile: Show (Touch accessibility)
    show_legend_bool = True if compact_mode else False

    if compact_mode:
        margin_t = 0 if not title else 40
        margin_b = 50 
        margin_l = 20
        margin_r = 20
        legend_y = -0.1
    else:
        # Desktop (Immersive)
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
            y=legend_y,
            xanchor="center",
            x=0.5,
            font=dict(color='#E5E7EB', size=11, family="Inter"),
            itemwidth=70,  
            bgcolor='rgba(0,0,0,0)',
        ),
        height=final_height, 
        margin=dict(t=margin_t, b=margin_b, l=margin_l, r=margin_r), 
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Inter", color="#9CA3AF"),
        annotations=[dict(text=f"{total_value:,.0f} €", x=0.5, y=0.5, font_size=22, showarrow=False, font=dict(family="JetBrains Mono", color="white", weight=700))] if total_value > 0 else []
    )
    
    fig.update_traces(hole=0.60, hoverinfo="label+percent+value")
    
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
    Create a modern area chart for portfolio performance.
    Includes native Range Selector.
    
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
        line=dict(color='#3b82f6', width=2.5),
        fill='tozeroy', 
        fillcolor='rgba(59, 130, 246, 0.12)',
        hovertemplate=f'<b>Net Worth</b>: {val_fmt}<extra></extra>'
    ))
    
    # Layout Configuration
    if compact_mode:
        # Mobile: compact sizing
        title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(size=14, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 40
        margin_b = 30
        chart_height = 420
    else:
        # Desktop: full sizing
        title_dict = dict(text="") if not title else dict(text=title, x=0, xref="container", font=dict(size=18, family="JetBrains Mono", color="#e6e6e6"))
        margin_t = 0 if not title else 60
        margin_b = 80
        chart_height = 520
    
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
                font=dict(color='#FFFFFF', size=11, weight=700),
                y=1.02,
                x=0,
                xanchor='left'
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
        margin=dict(t=margin_t + 30, b=margin_b + 30, l=0, r=20),
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
