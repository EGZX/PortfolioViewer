"""
Corporate Actions Configuration

Manually defined corporate actions (spin-offs, mergers) that are not reliably 
available from yfinance or other APIs.

Format:
{
    "TICKER": [
        {
            "date": "YYYY-MM-DD",
            "type": "SpinOff" | "Merger",
            ... action-specific fields
        }
    ]
}

Copyright (c) 2026 Andre. All rights reserved.
"""

# Spin-off examples:
# - PayPal (PYPL) from eBay (EBAY) - 2015-07-17
# - Kraft (KRFT) / Mondelez (MDLZ) from Kraft Foods - 2012-10-01

CORPORATE_ACTIONS = {
    # Example: PayPal spin-off from eBay
    "EBAY": [
        {
            "date": "2015-07-17",
            "type": "SpinOff",
            "new_ticker": "PYPL",
            "spin_off_ratio": 1.0,  # 1 PYPL share per 1 EBAY share
            "cost_basis_allocation": 0.20,  # 20% of cost basis goes to PYPL
            "notes": "PayPal spin-off from eBay"
        }
    ],
    
    # Example: Mondelez spin-off from Kraft Foods
    "KRFT": [
        {
            "date": "2012-10-01",
            "type": "SpinOff",
            "new_ticker": "MDLZ",
            "spin_off_ratio": 1.0,
            "cost_basis_allocation": 0.33,  # 33% to Mondelez
            "notes": "Mondelez International spin-off from Kraft Foods"
        }
    ],
    
    # Add your own corporate actions here:
    # "YOUR_TICKER": [
    #     {
    #         "date": "YYYY-MM-DD",
    #         "type": "SpinOff",
    #         "new_ticker": "NEW",
    #         "spin_off_ratio": 1.0,
    #         "cost_basis_allocation": 0.25,
    #         "notes": "Description"
    #     }
    # ],
}

# Mergers configuration (stock-for-stock or cash mergers)
MERGERS = {
    # Example structure (not real):
    # "ACQUIRED_TICKER": [
    #     {
    #         "date": "YYYY-MM-DD",
    #         "type": "Merger",
    #         "acquiring_ticker": "ACQUIRER",
    #         "exchange_ratio": 1.5,  # 1.5 shares of acquirer per 1 share
    #         "cash_in_lieu": 10.00,  # Optional cash component
    #         "notes": "Merger description"
    #     }
    # ],
}
