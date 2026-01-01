# -----------------------------------------------------------------------------
# (c) 2026 Andreas Wagner. All Rights Reserved.
#
# This code is part of the Portfolio Viewer project.
# Unauthorized usage or distribution is not permitted.
# -----------------------------------------------------------------------------

"""
Reusable UI Components
"""

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
            # Add directional arrows for accessibility (not just color)
            icon = "↑ " if m.get('delta_color') == 'pos' else "↓ " if m.get('delta_color') == 'neg' else "→ "
            delta_html = f'<div class="metric-delta {color_class}">{icon}{m["delta"]}</div>'
            
        # Wrapper for bar design
        items_html += f'<div class="kpi-item"><div class="kpi-content-bar">'
        items_html += f'<div class="kpi-label">{m["label"]}</div>'
        items_html += f'<div class="kpi-value-row"><div class="kpi-value">{m["value"]}</div>{delta_html}</div>'
        items_html += f'</div></div>'
        
    # Flatten string to avoid Markdown code block interpretation
    html = '<div class="kpi-board">'
    if title:
        html += f'<div class="kpi-header">{title}</div>'
    
    # Determine grid layout based on metric count
    grid_class = "kpi-grid-9" if len(metrics) > 6 else "kpi-grid-6"
    html += f'<div class="kpi-grid {grid_class}">'
    html += items_html
    html += '</div></div>'
    
    return html
