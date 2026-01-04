"""Portfolio state reconstruction and valuation."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Dict, List, Optional, Tuple
import pandas as pd

from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from lib.utils.logging_config import setup_logger
from lib.market_data import get_fx_rate, get_currency_for_ticker
from lib.market_cache import get_market_cache

logger = setup_logger(__name__)

# Brokers that track cash balances in their export  
CASH_TRACKING_BROKERS = frozenset([
    'scalable_capital',
    'trade_republic',
    'interactive_brokers',
    'flatex'
])

@dataclass
class Position:
    """Represents a current holding position."""
    ticker: str
    isin: Optional[str] = None
    name: Optional[str] = None
    shares: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)
    market_value: Decimal = Decimal(0)
    gain_loss: Decimal = Decimal(0)
    gain_loss_pct: Decimal = Decimal(0)
    currency: str = "EUR"
    asset_type: 'AssetType' = None

    def update_market_value(self, price: Decimal):
        """Update market value based on current price."""
        self.market_value = self.shares * price
        if self.cost_basis != 0:
            self.gain_loss = self.market_value - self.cost_basis
            self.gain_loss_pct = (self.gain_loss / self.cost_basis) * 100
        else:
            self.gain_loss = self.market_value
            self.gain_loss_pct = Decimal(0)

class Portfolio:
    """Portfolio state manager."""
    
    def __init__(self, transactions: List[Transaction]):
        self.transactions = sorted(transactions, key=lambda t: t.date)
        self.holdings: Dict[str, Position] = {}  # ticker -> Position
        
        # Cash balance tracking
        # Accurately determining cash balance requires the full transaction history.
        # Manual override available via set_cash_balance()
        self.cash_balance = Decimal(0)
        
        self.total_invested = Decimal(0)
        self.total_withdrawn = Decimal(0)
        self.total_dividends = Decimal(0)
        self.total_fees = Decimal(0)
        self.total_interest = Decimal(0)
        self.total_realized_pl = Decimal(0)  # Track realized gains/losses
        self.invested_capital = Decimal(0)
        self.realized_gains = Decimal(0)
        self.cash_flows: List[Tuple[datetime, Decimal]] = []  # List of (date, amount) for XIRR
        
        self._reconstruct_state()
    
    def process_transaction(self, t: Transaction):
        """Update portfolio state with a single transaction."""
        # Transaction totals are already normalized to EUR in pipeline
        amount_eur = t.total
        
        # Fees are already normalized to EUR
        fees_eur = t.fees if t.fees else Decimal(0)
        self.total_fees += fees_eur
        
        # Cash balance excludes stock transfers (only actual cash movements)
        should_update_cash = True
        
        if t.type in [TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT]:
            # Stock transfers (with ticker) don't affect cash balance
            if t.ticker and t.ticker.strip() != '':
                should_update_cash = False
        
        # Cash balance tracking rules:
        # Only track for specific brokers and exclude crypto assets
        tracks_cash = (
            t.broker 
            and t.broker in CASH_TRACKING_BROKERS 
            and t.asset_type != AssetType.CRYPTO
        )

        if should_update_cash and tracks_cash:
            # Uninvested cash balance calculation
            # Track ALL cash movements: deposits, withdrawals, buys, sells, dividends, fees
            old_balance = self.cash_balance
            
            if t.type == TransactionType.TRANSFER_OUT and (not t.ticker or t.ticker.strip() == ''):
                # Cash withdrawal - amount is positive but reduces cash
                self.cash_balance -= abs(amount_eur)
            elif t.type == TransactionType.BUY:
                # Buying stock - amount is negative, reduces cash
                self.cash_balance += amount_eur  # negative + negative = more negative
            elif t.type == TransactionType.SELL:
                # Selling stock - amount is positive, increases cash
                self.cash_balance += amount_eur
            elif t.type == TransactionType.TRANSFER_IN and (not t.ticker or t.ticker.strip() == ''):
                # Cash deposit - amount is positive, increases cash
                self.cash_balance += amount_eur
            elif t.type == TransactionType.DIVIDEND:
                # Dividend - amount is positive, increases cash
                self.cash_balance += amount_eur
            elif t.type == TransactionType.INTEREST:
                # Interest - amount is positive, increases cash
                self.cash_balance += amount_eur
            elif t.type in [TransactionType.COST, TransactionType.FEE]:
                # Fees - reduce cash
                self.cash_balance -= abs(amount_eur)
            
            # Log significant changes
            change = self.cash_balance - old_balance
            if abs(change) > 100:  # Only log changes > €100
                logger.info(f"[CASH] {t.date} {t.type.name} {t.ticker or 'CASH'}: €{old_balance:.2f} + €{change:.2f} = €{self.cash_balance:.2f}")
        
        # Track cash flows for XIRR
        # Inflows (Buys) are negative for wallet.
        if t.type == TransactionType.TRANSFER_IN:
            # TRANSFER_IN can be cash deposit OR stock transfer
            # Only count CASH deposits towards invested_capital
            if not t.ticker or t.ticker.strip() == '':
                # Cash-only transfer = actual deposit
                self.cash_flows.append((t.date, -amount_eur))
                self.invested_capital += amount_eur
                self.total_invested += abs(amount_eur)
            
        elif t.type == TransactionType.TRANSFER_OUT:
            # TRANSFER_OUT can be cash withdrawal OR stock transfer
            # Only count CASH withdrawals towards invested_capital
            if not t.ticker or t.ticker.strip() == '':
                # Cash-only transfer = actual withdrawal
                self.cash_flows.append((t.date, abs(amount_eur)))  # Positive for XIRR (money returned)
                self.invested_capital -= abs(amount_eur)
                self.total_withdrawn += abs(amount_eur)
        
        elif t.type == TransactionType.DEPOSIT:
            # Cash deposit (similar to TRANSFER_IN)
            self.cash_flows.append((t.date, -amount_eur))
            self.invested_capital += amount_eur
            self.total_invested += abs(amount_eur)
        
        elif t.type == TransactionType.WITHDRAWAL:
            # Cash withdrawal (similar to TRANSFER_OUT)
            self.cash_flows.append((t.date, abs(amount_eur)))
            self.invested_capital += amount_eur
            self.total_withdrawn += abs(amount_eur)
        
        # Update holdings for transactions with tickers
        if t.ticker and t.ticker.strip():
            # Use ISIN as primary key ("Asset ID") if available (stable), else fallback to ticker
            # This ensures we track positions stably even if tickers change
            key = t.isin if t.isin else t.ticker
            
            if key not in self.holdings:
                self.holdings[key] = Position(
                    ticker=t.ticker, 
                    isin=t.isin, 
                    name=t.name,
                    asset_type=t.asset_type,
                    currency=t.original_currency
                )
            
            pos = self.holdings[key]
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
                    pos.asset_type = AssetType.infer_from_ticker(t.ticker)
            
            # Increase Position
            if t.type in [TransactionType.BUY, TransactionType.TRANSFER_IN, TransactionType.STOCK_DIVIDEND]:
                pos.shares += t.shares
                
                # Cost Basis tracked in EUR
                amt_native = abs(amount_eur)
                
                # Stock dividends have no cost basis
                if t.type == TransactionType.STOCK_DIVIDEND:
                    amt_native = Decimal(0)
                
                # CASH transfers and FX currency pairs should not add to cost basis
                # These represent cash movements, not stock acquisitions
                elif t.type == TransactionType.TRANSFER_IN:
                    ticker_upper = t.ticker.upper() if t.ticker else ""
                    # Check if it's CASH or an FX pair (e.g., EUR.USD, USD.JPY)
                    is_cash_or_fx = (
                        ticker_upper == 'CASH' or 
                        '.' in ticker_upper  # FX pairs contain a dot (e.g., EUR.USD)
                    )
                    if is_cash_or_fx:
                        amt_native = Decimal(0)
                        logger.debug(f"TRANSFER_IN {ticker_upper}: Excluding from cost basis (cash/FX movement)")
                
                pos.cost_basis += amt_native
                
            # Decrease Position
            elif t.type in [TransactionType.SELL, TransactionType.TRANSFER_OUT]:
                # Use strict key lookup (ISIN preferred)
                key = t.isin if t.isin else t.ticker
                
                if key in self.holdings:
                    pos = self.holdings[key]
                    
                    # Check if selling more than owned
                    if t.shares > pos.shares:
                        logger.warning(
                            f"{t.ticker}: Selling/Transferring more shares than owned! "
                            f"Type: {t.type.value}, Capping to zero. (Check source data)"
                        )
                        t.shares = pos.shares
                    
                    # Calculate cost basis for sold shares (proportional)
                    if pos.shares > 0:
                        cost_per_share = pos.cost_basis / (pos.shares + t.shares)
                        sold_cost_basis = cost_per_share * t.shares
                    else:
                        sold_cost_basis = Decimal(0)
                    
                    # Calculate realized gain/loss (only for SELL, not transfers)
                    if t.type == TransactionType.SELL:
                        # Proceeds from sale (in EUR)
                        proceeds_eur = abs(amount_eur)
                        # Realized gain = proceeds - cost basis
                        realized_gain_loss = proceeds_eur - sold_cost_basis
                        self.realized_gains += realized_gain_loss
                        self.total_realized_pl += realized_gain_loss
                    
                    # Update shares
                    pos.shares -= t.shares
                    
                    # Update cost basis (proportional reduction)
                    if pos.shares > 0:
                        pos.cost_basis -= sold_cost_basis
                    else:
                        # Sold all shares
                        pos.cost_basis = Decimal(0)
                else:
                    logger.warning(f"{t.ticker}: Sell transaction but no position found. Ignoring.")
            
            elif t.type == TransactionType.DIVIDEND:
                self.total_dividends += abs(amount_eur)
                # Add to XIRR cash flows (positive = return to investor)
                self.cash_flows.append((t.date, abs(amount_eur)))
            
            elif t.type == TransactionType.COST:
                self.total_fees += abs(amount_eur)
                # Add to XIRR cash flows (negative = cost to investor)
                self.cash_flows.append((t.date, -abs(amount_eur)))

        # Handle Interest
        if t.type == TransactionType.INTEREST:
            self.total_interest += abs(amount_eur)
            # Add to XIRR cash flows (positive = return to investor)
            self.cash_flows.append((t.date, abs(amount_eur)))
        
    def _reconstruct_state(self):
        """Reconstruct current portfolio state from all transactions."""
        logger.info(f"Reconstructing portfolio from {len(self.transactions)} transactions")
        
        # Sort transactions by date
        self.transactions.sort(key=lambda x: x.date if hasattr(x, 'date') else datetime.min)
        
        if self.transactions:
            logger.debug("First 5 transactions preview:")
            for t in self.transactions[:5]:
                t_ticker = t.ticker if t.ticker else "N/A"
                logger.debug(f"{t.date.date() if hasattr(t.date, 'date') else t.date} | {t.type.value:<15} | {t_ticker:<12} | {t.shares:<10.4f} | {t.total:.2f}")

        for t in self.transactions:
            self.process_transaction(t)
            
        # Filter out closed positions
        self.holdings = {k: v for k, v in self.holdings.items() if abs(v.shares) > 0.000001}
        
        logger.info(f"Portfolio state rebuilt: {len(self.holdings)} holdings active.")
                   
    def get_unique_tickers(self) -> List[str]:
        """Get list of all unique tickers with current holdings."""
        # Return tickers from positions (handle ISIN-keyed map)
        return list(set(pos.ticker for pos in self.holdings.values() if pos.ticker))
    
    def calculate_total_value(self, prices: Dict[str, Optional[float]]) -> Decimal:
        """Calculate total portfolio value (holdings + cash) in EUR."""
        from datetime import date, timedelta
        from lib.market_cache import get_market_cache
        
        holdings_value = Decimal(0)
        
        logger.info(f"[NET_WORTH] Starting calculation for {len(self.holdings)} holdings")
        for key, pos in self.holdings.items():
            if pos.shares <= 0:
                continue
                
            # Position tracks the ticker regardless of what the key is (ISIN/Ticker)
            ticker = pos.ticker
            price_currency = get_currency_for_ticker(ticker)
            current_price = prices.get(ticker)
            
            # Try to get a price with fallback mechanism
            if current_price is not None:
                pos.update_market_value(Decimal(str(current_price)))
            else:
                # Fallback 1: Try cached price from last 90 days
                try:
                    cache = get_market_cache()
                    for days_ago in range(1, 90):
                        check_date = date.today() - timedelta(days=days_ago)
                        cached_price = cache.get_price(ticker, check_date)
                        if cached_price:
                            current_price = cached_price
                            pos.update_market_value(Decimal(str(current_price)))
                            logger.debug(f"{ticker}: Using cached price from {check_date}")
                            break
                except Exception as e:
                    logger.error(f"Failed to get cached price for {ticker}: {e}")
                
                # Fallback 2: Use average cost basis
                if current_price is None:
                    avg_cost_per_share = pos.cost_basis / pos.shares if pos.shares > 0 else Decimal(0)
                    current_price = float(avg_cost_per_share)
                    pos.update_market_value(avg_cost_per_share)
                    price_currency = "EUR"  # Cost basis is always in EUR
                    logger.debug(f"{ticker}: Using cost basis as price")
            
            # Convert to EUR based on Price Source currency
            position_val_eur = pos.market_value
            if price_currency != "EUR":
                # Fetch FX rate (should be cached) and convert to Decimal
                rate = get_fx_rate(price_currency, "EUR")
                position_val_eur = position_val_eur * Decimal(str(rate))
            
            logger.debug(f"[NET_WORTH] {ticker}: {pos.shares} shares * {current_price} {price_currency} = {pos.market_value} {price_currency} → €{position_val_eur:.2f}")
            holdings_value += position_val_eur
        
        logger.debug(f"[NET_WORTH] Holdings total: €{holdings_value:.2f}, Cash: €{self.cash_balance:.2f}")
        total = holdings_value + self.cash_balance
        return total
    
    def calculate_performance_history_optimized(
        self,
        price_history: pd.DataFrame,
        start_date: datetime,
        end_date: datetime
    ) -> Tuple[List[str], List[float], List[float], List[float]]:
        """
        Calculates daily portfolio value efficiently using cached price history DataFrame.
        
        Args:
            price_history: DataFrame with Date index and Ticker columns (prices)
            start_date: Start of calculations
            end_date: End of calculations
            
        Returns:
            Tuple of (dates, net_deposits, portfolio_values, cost_basis_values)
        """
        # Ensure we have data
        if not self.transactions:
            return [], [], [], []
            
        # Re-index price history to daily frequency (ffill for weekends/holidays)
        s_date = start_date.date() if hasattr(start_date, 'date') else start_date
        e_date = end_date.date() if hasattr(end_date, 'date') else end_date
        
        # Cap end_date at today to prevent future plotting
        today = date.today()
        if e_date > today:
            e_date = today
            
        date_range = pd.date_range(start=s_date, end=e_date, freq='D')
        
        # Handle empty price history
        if not price_history.empty:
            price_history.index = pd.to_datetime(price_history.index)
            # Reindex to full range and forward fill missing prices
            full_prices = price_history.reindex(date_range, method='ffill')
        else:
            full_prices = pd.DataFrame(index=date_range)
            
        # Convert DF to dict for O(1) lookups: {date: {ticker: price}}
        price_lookup = {}
        if not full_prices.empty:
            # Timestamp -> {ticker: price}
            temp_dict = full_prices.to_dict('index')
            price_lookup = {
                ts.date(): prices 
                for ts, prices in temp_dict.items()
            }
            
        # Initialize runner portfolio
        # We need a fresh portfolio state that we advance day by day
        running_portfolio = Portfolio([]) # Empty start
        
        # Process transactions by date
        sorted_trans = sorted(self.transactions, key=lambda t: t.date)
        trans_idx = 0
        num_trans = len(sorted_trans)
        
        dates_list = []
        net_deposits_list = []
        value_list = []
        cost_basis_list = []
        
        for current_ts in date_range:
            current_date = current_ts.date()
            
            # Process transactions for this day
            while trans_idx < num_trans and sorted_trans[trans_idx].date.date() <= current_date:
                running_portfolio.process_transaction(sorted_trans[trans_idx])
                trans_idx += 1
            
            # Only record if we have started investing
            if trans_idx > 0:
                # Calculate Value
                daily_prices = price_lookup.get(current_date, {})
                
                # Convert the dataframe row dict to optional floats
                clean_prices = {
                    k: float(v) if pd.notna(v) else None 
                    for k, v in daily_prices.items()
                }
                
                total_value = running_portfolio.calculate_total_value(clean_prices)
                
                # Get Cost Basis
                total_cost_basis = sum(pos.cost_basis for pos in running_portfolio.holdings.values())
                
                dates_list.append(current_date.strftime('%Y-%m-%d'))
                net_deposits_list.append(float(running_portfolio.invested_capital))
                value_list.append(float(total_value))
                cost_basis_list.append(float(total_cost_basis))
                
        return dates_list, net_deposits_list, value_list, cost_basis_list

    def get_holdings_summary(self, prices: Dict[str, Optional[float]]) -> pd.DataFrame:
        """Get summary of all holdings as DataFrame (excludes zero-share positions)."""
        logger.info("[PERF] Starting get_holdings_summary")
        data = []
        
        for idx, (key, pos) in enumerate(self.holdings.items()):
            # Use ticker from position for display/lookup
            ticker = pos.ticker
            # Skip closed positions
            if pos.shares <= 0:
                continue
            
            logger.info(f"[PERF] Holdings summary {idx+1}: {ticker}")
            
            # Determine the currency of the price
            price_currency = get_currency_for_ticker(ticker)
            logger.info(f"[PERF] Currency for {ticker}: {price_currency}")
            
            # Get current price
            current_price = prices.get(ticker)
            
            if current_price is not None:
                pos.update_market_value(Decimal(str(current_price)))
            else:
                # Fallback: Cached price
                try:
                    cache = get_market_cache()
                    
                    # Try the last 90 days for a price
                    for days_ago in range(1, 90):
                        check_date = date.today() - timedelta(days=days_ago)
                        cached_price = cache.get_price(ticker, check_date)
                        if cached_price:
                            current_price = cached_price
                            pos.update_market_value(Decimal(str(current_price)))
                            logger.warning(f"{ticker}: Using cached price from {check_date} ({cached_price:.2f} {price_currency})")
                            break
                except Exception as e:
                    logger.error(f"Failed to get cached price for {ticker}: {e}")
                
                # Fallback: Average cost
                if current_price is None:
                    avg_cost_per_share = pos.cost_basis / pos.shares if pos.shares > 0 else Decimal(0)
                    current_price = float(avg_cost_per_share)
                    pos.update_market_value(avg_cost_per_share)
                    price_currency = "EUR"  # Cost basis is always in EUR
                    logger.warning(f"{ticker}: No price found, using average cost basis ({current_price:.2f} EUR)")

            # Convert price to EUR for display
            current_price_eur = current_price
            if price_currency != "EUR" and current_price:
                try:
                    logger.info(f"[PERF] Getting FX rate for {price_currency}/EUR")
                    fx_rate = get_fx_rate(price_currency, "EUR")
                    logger.info(f"[PERF] FX rate {price_currency}/EUR retrieved: {fx_rate}")
                    current_price_eur = current_price * float(fx_rate)
                except Exception as e:
                    logger.error(f"Failed to get FX rate for {price_currency}/EUR: {e}")
                    current_price_eur = current_price
            
            # Calculate market value in EUR
            market_value_eur = float(pos.shares) * current_price_eur
            
            # Calculate metrics
            avg_cost = pos.cost_basis / pos.shares if pos.shares > 0 else 0
            gain_loss_eur = market_value_eur - float(pos.cost_basis)
            gain_loss_pct = (gain_loss_eur / float(pos.cost_basis) * 100) if pos.cost_basis > 0 else 0
            
            # Get asset type display name
            asset_type_display = pos.asset_type.value if pos.asset_type else "Unknown"
            
            data.append({
                'Ticker': ticker,
                'Name': pos.name if pos.name else ticker,
                'Asset Type': asset_type_display,
                'Shares': float(pos.shares),
                'Avg Cost (EUR)': float(avg_cost),
                'Current Price (EUR)': current_price_eur,
                'Market Value (EUR)': market_value_eur,
                'Gain/Loss (EUR)': gain_loss_eur,
                'Gain %': gain_loss_pct
            })
        
        logger.info("[PERF] get_holdings_summary complete")
        df = pd.DataFrame(data)
        if not df.empty:
            # Calculate allocation percentages
            total_portfolio_value = df['Market Value (EUR)'].sum()
            df['Allocation %'] = (df['Market Value (EUR)'] / total_portfolio_value * 100)
            
            df = df.sort_values('Market Value (EUR)', ascending=False)
            # Reorder columns
            cols = ['Ticker', 'Name', 'Asset Type', 'Shares', 'Avg Cost (EUR)', 
                    'Current Price (EUR)', 'Market Value (EUR)', 'Allocation %', 
                    'Gain/Loss (EUR)', 'Gain %']
            df = df[cols]
        
        return df
    
    def get_cash_flows_for_xirr(self, current_value: Decimal) -> Tuple[List[datetime], List[float]]:
        """
        Prepare cash flows for XIRR calculation.
        
        Only includes EXTERNAL cash flows (TRANSFER_IN/OUT, DIVIDEND, INTEREST, COST).
        Excludes internal position changes (BUY/SELL) as those are portfolio rebalancing.
        
        Returns: (dates, amounts) where amounts are negative for investments, positive for returns.
        """
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
        
        return dates, amounts
