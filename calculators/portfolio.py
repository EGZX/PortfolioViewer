"""Portfolio state reconstruction and valuation."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Dict, List, Optional, Tuple
import pandas as pd

from parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from utils.logging_config import setup_logger
from services.market_data import get_fx_rate, get_currency_for_ticker
from services.market_cache import get_market_cache
from datetime import date, timedelta

logger = setup_logger(__name__)

# Brokers that track cash balances in their export
CASH_TRACKING_BROKERS = frozenset([
    'Scalable Capital',
    'Trade Republic'
])

@dataclass
class Position:
    """Represents a current holding position."""
    ticker: str
    name: Optional[str] = None
    shares: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)
    market_value: Decimal = Decimal(0)
    gain_loss: Decimal = Decimal(0)
    gain_loss_pct: Decimal = Decimal(0)
    currency: str = "EUR"
    asset_type: 'AssetType' = None  # Will be set from transaction

    def update_market_value(self, price: Decimal):
        """Update market value based on current price."""
        self.market_value = self.shares * price
        if self.cost_basis != 0:
            self.gain_loss = self.market_value - self.cost_basis
            self.gain_loss_pct = (self.gain_loss / self.cost_basis) * 100
        else:
            self.gain_loss = self.market_value
            self.gain_loss_pct = Decimal(0)

class Portfolio: # Renamed from PortfolioCalculator to Portfolio to match original class name
    """Portfolio state manager.""" # Original docstring
    
    def __init__(self, transactions: List[Transaction]):
        self.transactions = sorted(transactions, key=lambda t: t.date)
        self.holdings: Dict[str, Position] = {}  # ticker -> Position
        
        # NOTE: cash_balance cannot be accurately calculated from transaction history alone
        # when the CSV only contains partial history. It would need the starting cash balance.
        # For now, set to 0 and allow manual override via set_cash_balance()
        self.cash_balance = Decimal(0)  # Will be set manually or from broker data
        
        self.total_invested = Decimal(0) # Kept original attribute name
        self.total_withdrawn = Decimal(0) # Kept original attribute name
        self.total_dividends = Decimal(0) # Kept original attribute name
        self.total_fees = Decimal(0) # Kept original attribute name
        self.total_interest = Decimal(0)  # New: Track total interest
        self.invested_capital = Decimal(0) # New attribute from the provided code
        self.realized_gains = Decimal(0)  # Track realized gains from selling
        self.cash_flows = []  # List of (date, amount) for XIRR # New attribute from the provided code
        
        self._reconstruct_state()
    
    def process_transaction(self, t: Transaction):
        """Update portfolio state with a single transaction."""
        # Transaction totals are already in EUR from CSV parser
        amount_eur = t.total
        
        # Convert and track fees
        if t.fees:
            fees_eur = t.fees * t.fx_rate if t.original_currency != 'EUR' else t.fees
            self.total_fees += fees_eur
        
        # Cash balance excludes stock transfers (only actual cash movements)
        should_update_cash = True
        
        if t.type in [TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT]:
            # Stock transfers (with ticker) don't affect cash balance
            if t.ticker and t.ticker.strip() != '':
                should_update_cash = False
        
        # Cash balance tracking rules:
        # Only track for specific brokers (Scalable Capital, Trade Republic)
        # Exclude crypto assets regardless of broker
        tracks_cash = (
            t.broker 
            and t.broker in CASH_TRACKING_BROKERS 
            and t.asset_type != AssetType.CRYPTO
        )

        if should_update_cash and tracks_cash:
            # For TRANSFER_OUT, the total is positive (money leaving portfolio)
            # So we need to SUBTRACT it
            if t.type == TransactionType.TRANSFER_OUT and (not t.ticker or t.ticker.strip() == ''):
                self.cash_balance -= abs(amount_eur)  # Subtract withdrawals
            else:
                self.cash_balance += amount_eur  # Add all other cash transactions
        
        # Track cash flows for XIRR
        # Inflows (Buys) are negative for wallet, but positive investment flow? 
        # XIRR expects: Dates, Amounts. 
        # Deposit/Buy: Negative (cash out of pocket)
        # Withdraw/Sell: Positive (cash into pocket)
        # BUT: For Portfolio XIRR, we usually track transfer IN/OUT as external flows.
        # Buys/Sells are internal if we track cash account.
        
        # If we assume the Portfolio includes Cash:
        # Transfer In -> Cash Increases (Negative Flow for XIRR? No, usually Transfer In is synonymous with Deposit)
        # Standard XIRR:
        # - Deposit: Negative (money left me to go to port)
        # - Withdraw: Positive (money came back)
        # - Current Value: Positive (theoretical withdrawal)
        
        # Logic:
        # t.total is change in CASH balance.
        # Buy: total < 0. Cash goes down. Stock goes up. Internal swap?
        # If we track the WHOLE portfolio (Cash + Stock), Buys are neutral.
        # ONLY TransferIn/TransferOut affects the "External" flows.
        
        if t.type == TransactionType.TRANSFER_IN:
            # TRANSFER_IN can be cash deposit OR stock transfer
            # Only count CASH deposits towards invested_capital
            if not t.ticker or t.ticker.strip() == '':
                # Cash-only transfer = actual deposit
                self.cash_flows.append((t.date, -amount_eur))
                self.invested_capital += amount_eur
                self.total_invested += abs(amount_eur)
            # else: Stock transfer - doesn't affect invested_capital
            
        elif t.type == TransactionType.TRANSFER_OUT:
            # TRANSFER_OUT can be cash withdrawal OR stock transfer
            # Only count CASH withdrawals towards invested_capital
            if not t.ticker or t.ticker.strip() == '':
                # Cash-only transfer = actual withdrawal
                # TRANSFER_OUT has POSITIVE value in CSV (money out)
                # So we SUBTRACT it from invested_capital
                self.cash_flows.append((t.date, abs(amount_eur)))  # Positive for XIRR (money returned)
                self.invested_capital -= abs(amount_eur)  # SUBTRACT withdrawals
                self.total_withdrawn += abs(amount_eur)
            # else: Stock transfer - doesn't affect invested_capital
        
        elif t.type == TransactionType.DEPOSIT:
            # Cash deposit (similar to TRANSFER_IN)
            self.cash_flows.append((t.date, -amount_eur))  # Negative (investment)
            self.invested_capital += amount_eur
            self.total_invested += abs(amount_eur)
        
        elif t.type == TransactionType.WITHDRAWAL:
            # Cash withdrawal (similar to TRANSFER_OUT)
            self.cash_flows.append((t.date, abs(amount_eur)))  # Positive (return)
            self.invested_capital += amount_eur  # amount_eur is negative
            self.total_withdrawn += abs(amount_eur)
            
        # Update holdings
        # Update holdings
            if t.ticker not in self.holdings:
                self.holdings[t.ticker] = Position(
                    ticker=t.ticker, 
                    name=t.name,
                    asset_type=t.asset_type,
                    currency=t.original_currency
                )
            
            pos = self.holdings[t.ticker]
            # Use transaction name if position name is missing
            if not pos.name and t.name:
                pos.name = t.name
            # Update asset_type if transaction has better info
            if t.asset_type and t.asset_type != AssetType.UNKNOWN:
                pos.asset_type = t.asset_type
            # If still unknown, try to infer from name
            elif pos.asset_type == AssetType.UNKNOWN or not pos.asset_type:
                inferred_type = AssetType.infer_from_name(pos.name or t.name or "")
                if inferred_type:
                    pos.asset_type = inferred_type
                else:
                    # Fallback to ticker-based inference
                    pos.asset_type = AssetType.infer_from_ticker(t.ticker)
            
            # INCREASE POSITION
            if t.type in [TransactionType.BUY, TransactionType.TRANSFER_IN, TransactionType.STOCK_DIVIDEND]:
                pos.shares += t.shares
                
                # For transfers, we assume cost basis increases by the value transferred (if provided)
                # t.total is negative for outflows (Buys), but for TransferIn it depends on sign convention.
                # Standard: TransferIn is "Money In", total > 0. But stock value?
                # Usually TransferIn comes with a cost basis or market value.
                # If t.total is the Value, it increases cost basis.
                # Logic: cost_basis += abs(amount_eur)
                # But wait, earlier we subtract amount_eur for BUYS (because amount is negative).
                # Let's trust absolute value for cost basis increment.
                amt = abs(amount_eur)
                if t.type == TransactionType.STOCK_DIVIDEND:
                    amt = 0 # Usually 0 cost
                
                pos.cost_basis += amt
                
            # DECREASE POSITION
            elif t.type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
                if pos.shares > 0:
                    # Pro-rata reduce cost basis
                    cost_per_share = pos.cost_basis / pos.shares
                    # Safe handling if t.shares > pos.shares (partial sale of everything owned)
                    shares_to_remove = min(t.shares, pos.shares)
                    
                    sold_cost = cost_per_share * shares_to_remove
                    pos.cost_basis -= sold_cost
                    
                    # Track realized gain from CSV (for SELL transactions)
                    # The CSV already has the correct realized gain calculated
                    if t.type == TransactionType.SELL and t.realized_gain != 0:
                        self.realized_gains += t.realized_gain
                
                pos.shares -= t.shares
                
                # CRITICAL: Cap to prevent negative holdings
                if pos.shares < 0:
                    logger.warning(
                        f"{t.ticker}: Selling/Transferring more shares than owned! "
                        f"Type: {t.type.value}, "
                        f"Qty: {t.shares}, "
                        f"Had: {pos.shares + t.shares}, "
                        f"Capping to zero."
                    )
                    pos.shares = Decimal(0)
                    pos.cost_basis = Decimal(0)
            
            elif t.type == TransactionType.DIVIDEND:
                self.total_dividends += abs(amount_eur)
                # Add to XIRR cash flows (positive = return to investor)
                self.cash_flows.append((t.date, abs(amount_eur)))
            
            elif t.type == TransactionType.INTEREST:
                self.total_interest += abs(amount_eur)
                # Add to XIRR cash flows (positive = return to investor)
                self.cash_flows.append((t.date, abs(amount_eur)))
            
            elif t.type == TransactionType.COST:
                self.total_fees += abs(amount_eur)
                # Add to XIRR cash flows (negative = cost to investor)
                self.cash_flows.append((t.date, -abs(amount_eur)))
        
    def _reconstruct_state(self):
        """Reconstruct current portfolio state from all transactions."""
        logger.info(f"Reconstructing portfolio from {len(self.transactions)} transactions")
        
        for trans in self.transactions:
            self.process_transaction(trans) # Call the new process_transaction method
        
        # Remove holdings with zero shares
        self.holdings = {
            ticker: holding
            for ticker, holding in self.holdings.items()
            if holding.shares > 0
        }
        
        logger.info(f"Portfolio state: {len(self.holdings)} holdings, "
                   f"€{self.cash_balance:.2f} cash, "
                   f"€{self.total_invested:.2f} invested")
    
    def get_unique_tickers(self) -> List[str]:
        """Get list of all unique tickers with current holdings."""
        return list(self.holdings.keys())
    
    def calculate_total_value(self, prices: Dict[str, Optional[float]]) -> Decimal:
        """Calculate total portfolio value (holdings + cash) in EUR."""
        holdings_value = Decimal(0)
        
        for ticker, pos in self.holdings.items():
            price = prices.get(ticker)
            if price is not None:
                pos.update_market_value(Decimal(str(price)))
            
            # Convert to EUR based on PRICE SOURCE currency (not position currency)
            price_currency = get_currency_for_ticker(ticker)
            
            position_val_eur = pos.market_value
            if price_currency != "EUR":
                # Fetch live FX rate
                rate = get_fx_rate(price_currency, "EUR")
                position_val_eur *= rate
                
            holdings_value += position_val_eur
        
        # Use cash_balance calculated from all cash-affecting transactions
        total = holdings_value + self.cash_balance
        logger.debug(f"Total value: €{total:.2f} (holdings: €{holdings_value:.2f}, cash: €{self.cash_balance:.2f})")
        
        return total
    
    def get_holdings_summary(self, prices: Dict[str, Optional[float]]) -> pd.DataFrame:
        """Get summary of all holdings as DataFrame (excludes zero-share positions)."""
        data = []
        
        for ticker, pos in self.holdings.items():
            # CRITICAL FIX: Skip positions with zero or negative shares
            if pos.shares <= 0:
                logger.debug(f"Skipping {ticker} with {pos.shares} shares (fully sold)")
                continue
            
            current_price = prices.get(ticker)
            if current_price is not None:
                pos.update_market_value(Decimal(str(current_price)))
            else:
                # FALLBACK: Try to get last cached price
                try:
                    cache = get_market_cache()
                    
                    # Try the last 90 days for a price
                    for days_ago in range(1, 90):
                        check_date = date.today() - timedelta(days=days_ago)
                        cached_price = cache.get_price(ticker, check_date)
                        if cached_price:
                            current_price = cached_price
                            pos.update_market_value(Decimal(str(current_price)))
                            logger.warning(f"{ticker}: Using cached price from {check_date} ({cached_price:.2f})")
                            break
                except Exception as e:
                    logger.error(f"Failed to get cached price for {ticker}: {e}")

            # Calculate metrics
            avg_cost = pos.cost_basis / pos.shares if pos.shares > 0 else 0
            
            # Get asset type display name
            asset_type_display = pos.asset_type.value if pos.asset_type else "Unknown"
            
            data.append({
                'Ticker': ticker,
                'Name': pos.name if pos.name else ticker,
                'Asset Type': asset_type_display,
                'Shares': float(pos.shares),
                'Avg Cost': float(avg_cost),
                'Current Price': float(current_price) if current_price else 0.0,
                'Market Value': float(pos.market_value),
                'Gain/Loss': float(pos.gain_loss),
                'Gain %': float(pos.gain_loss_pct)
            })
        
        df = pd.DataFrame(data)
        if not df.empty:
            df = df.sort_values('Market Value', ascending=False)
            # Reorder columns
            cols = ['Ticker', 'Name', 'Asset Type', 'Shares', 'Avg Cost', 'Current Price', 'Market Value', 'Gain/Loss', 'Gain %']
            df = df[cols]
        
        return df
    
    def get_cash_flows_for_xirr(self, current_value: Decimal) -> Tuple[List[datetime], List[float]]:
        """
        Prepare cash flows for XIRR calculation.
        
        CRITICAL: Only includes EXTERNAL cash flows (TRANSFER_IN/OUT, DIVIDEND, INTEREST, COST)
        Excludes internal position changes (BUY/SELL) as those are portfolio rebalancing.
        
        Returns: (dates, amounts) where amounts are negative for investments, positive for returns
        """
        # Cash flows are already tracked in self.cash_flows during process_transaction
        # They follow the correct sign convention:
        # - TRANSFER_IN, DEPOSIT: Negative (money invested)
        # - TRANSFER_OUT, WITHDRAWAL: Positive (money withdrawn)
        # - DIVIDEND, INTEREST: Positive (return to investor)
        # - COST: Negative (money out)
        
        # Aggregate by date (using timezone-aware datetime)
        aggregated: Dict[datetime, Decimal] = defaultdict(Decimal)
        
        for date, amount in self.cash_flows:
            # Quantize to 2 decimal places for consistency
            quantized_amount = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
            aggregated[date.date()] += quantized_amount
        
        # Add final liquidation value (today, timezone-aware)
        today = datetime.now(tz=timezone.utc).date()
        current_value_quantized = Decimal(str(current_value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
        aggregated[today] = aggregated.get(today, Decimal(0)) + current_value_quantized
        
        # Sort by date and convert to lists
        sorted_flows = sorted(aggregated.items())
        dates = [datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) for d, _ in sorted_flows]
        amounts = [float(amt) for _, amt in sorted_flows]
        
        logger.info(f"XIRR cash flows: {len(dates)} dates, "
                   f"total invested: {sum(a for a in amounts if a < 0):.2f}, "
                   f"total returned: {sum(a for a in amounts if a > 0):.2f}")
        
        return dates, amounts
