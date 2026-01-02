
def mask_currency(val, is_private):
    return "••••••" if is_private else f"€{val:,.0f}"

def mask_currency_precise(val, is_private):
    return "••••••" if is_private else f"€{val:,.2f}"
