# Portfolio Viewer v2.0 - Release Notes

This update brings significant improvements to data visualization, asset classification, and user experience.

## 🚀 Key Features

### 1. Enhanced Asset Classification
*   **Smart Detection**: ETFs, Crypto, and other asset types are now automatically detected based on their names (e.g., "Vanguard S&P 500 ETF" is identified as an ETF).
*   **Explicit "Asset Type" Column**: The Holdings table now clearly shows the type of each investment (Stock, ETF, Crypto, Cash, etc.).
*   **Filtering**: You can now filter your holdings by:
    *   **Assets Only**: Hides cash/deposit items.
    *   **Cash Only**: Shows only cash positions.
    *   **All**: Shows everything.
    *   *Note: Filtering is instant and does not reload the data.*

### 2. Performance Chart v2
The "Performance History" chart has been completely redesigned to be more insightful and responsive:
*   **Configurable Timeframe**: Select from 1 Month, 3 Months, 6 Months, 1 Year, or All Time.
*   **High Resolution**: Date points are now calculated weekly or daily depending on the timeframe (up from monthly), providing a much smoother curve.
*   **New Metrics**:
    *   🔵 **Net Deposits** (Blue Dotted): Total cash you have put in (Deposits - Withdrawals).
    *   🟠 **Cost Basis** (Orange Dashed): The purchase cost of your *current* holdings.
    *   🟢 **Net Worth** (Green Area): The current market value of your portfolio (Holdings + Cash).
*   **Why Cost Basis?**: The gap between "Net Deposits" and "Cost Basis" often explains realized gains or cash drag. The gap between "Cost Basis" and "Net Worth" shows your unrealized profit.

### 3. Allocation Chart
*   **Resolved Names**: The donut chart now displays company/fund names (e.g., "Apple Inc.") instead of obscure ISIN codes, making your portfolio allocation immediately understandable.

### 4. Smart Auto-Load
*   **Cache System**: Your transaction CSV is now securely cached locally after upload.
*   **Instant Logic**: When you open the app again, you'll see a **"Load Cached Data"** button. One click restores your dashboard instantly—no need to re-upload the CSV every time!

### 5. Data Accuracy
*   **Metric Clarification**:
    *   "Total Invested" renamed to **"Net Deposits"** for clarity.
    *   **"Absolute Gain"** is now calculated as: `Realized Gains + Dividends + Interest + (Current Value - Cost Basis)`.
*   **Cash Handling**: Improved logic for tracking cash balances from various transaction types (TransferIn/Out, Deposit/Withdrawal).

## 💡 How to Use
1.  **Filtering**: Use the "Filter by Type" dropdown above the Holdings table.
2.  **Chart Zoom**: Select a timeframe (e.g., "1Y") to zoom in on recent performance.
3.  **Tooltips**: Hover over the chart lines to see exactly how much you had invested vs. what it was worth on that date.

## Technical Improvements
*   Refactored `Portfolio` calculation for better performance.
*   Added `AssetType` name-based inference engine.
*   Implemented SQLite-based caching for transaction data.
*   Full code review and error handling enhancements.
