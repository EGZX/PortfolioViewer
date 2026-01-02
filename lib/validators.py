"""
Data Quality Validation Service

Provides comprehensive validation and quality checks for imported transaction data
to ensure accuracy and detect common issues.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple
from collections import defaultdict

from lib.parsers.enhanced_transaction import Transaction, TransactionType
from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


class ValidationIssue:
    """Represents a data quality issue."""
    
    SEVERITY_ERROR = "ERROR"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_INFO = "INFO"
    
    def __init__(self, severity: str, category: str, message: str, transaction: Transaction = None):
        self.severity = severity
        self.category = category
        self.message = message
        self.transaction = transaction
        self.transaction_ref = f"{transaction.date.date()} - {transaction.type.value}" if transaction else None


class DataValidator:
    """Validates transaction data quality and detects common issues."""
    
    def __init__(self):
        self.issues: List[ValidationIssue] = []
    
    def validate_all(self, transactions: List[Transaction]) -> List[ValidationIssue]:
        """Run all validation checks."""
        self.issues = []
        
        self.check_duplicates(transactions)
        self.check_orphaned_sells(transactions)
        self.check_sign_conventions(transactions)
        self.check_fx_rates(transactions)
        self.check_price_anomalies(transactions)
        self.check_data_completeness(transactions)
        self.check_date_order(transactions)
        
        # NEW: Corporate action detection
        self.detect_likely_missed_splits(transactions)
        self.detect_orphaned_positions(transactions)
        self.check_cached_price_history_for_splits(transactions)  # USES CACHED DATA!
        
        return self.issues
    
    def check_duplicates(self, transactions: List[Transaction]):
        """Detect potential duplicate transactions."""
        seen = {}
        
        for trans in transactions:
            # Create fingerprint: date + type + ticker + shares + price
            fingerprint = (
                trans.date.date(),
                trans.type,
                trans.ticker,
                trans.shares,
                trans.price
            )
            
            if fingerprint in seen:
                self.issues.append(ValidationIssue(
                    ValidationIssue.SEVERITY_WARNING,
                    "Duplicate",
                    f"Potential duplicate transaction detected (same date, type, ticker, shares, price)",
                    trans
                ))
            else:
                seen[fingerprint] = trans
    
    def check_orphaned_sells(self, transactions: List[Transaction]):
        """Check for sells before any buys (orphaned sells)."""
        holdings = defaultdict(Decimal)
        
        for trans in sorted(transactions, key=lambda t: t.date):
            if trans.ticker:
                if trans.type == TransactionType.BUY:
                    holdings[trans.ticker] += trans.shares
                elif trans.type == TransactionType.SELL:
                    if holdings[trans.ticker] < trans.shares:
                        self.issues.append(ValidationIssue(
                            ValidationIssue.SEVERITY_WARNING,
                            "Orphaned Sell",
                            f"Selling {trans.shares} shares of {trans.ticker} but only {holdings[trans.ticker]} owned",
                            trans
                        ))
                    holdings[trans.ticker] -= trans.shares
    
    def check_sign_conventions(self, transactions: List[Transaction]):
        """Validate that transaction totals follow expected sign conventions."""
        for trans in transactions:
            if trans.type == TransactionType.BUY:
                if trans.total > 0:
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_WARNING,
                        "Sign Convention",
                        f"BUY transaction has positive total ({trans.total}), expected negative",
                        trans
                    ))
            elif trans.type == TransactionType.SELL:
                if trans.total < 0:
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_WARNING,
                        "Sign Convention",
                        f"SELL transaction has negative total ({trans.total}), expected positive",
                        trans
                    ))
            elif trans.type in [TransactionType.DIVIDEND, TransactionType.INTEREST]:
                if trans.total < 0:
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_WARNING,
                        "Sign Convention",
                        f"{trans.type.value} has negative total ({trans.total}), expected positive",
                        trans
                    ))
    
    def check_fx_rates(self, transactions: List[Transaction]):
        """Check for unreasonable FX rates."""
        for trans in transactions:
            if trans.fx_rate < Decimal('0.01') or trans.fx_rate > Decimal('1000'):
                self.issues.append(ValidationIssue(
                    ValidationIssue.SEVERITY_ERROR,
                    "FX Rate",
                    f"Suspicious FX rate: {trans.fx_rate} for {trans.original_currency}",
                    trans
                ))
    
    def check_price_anomalies(self, transactions: List[Transaction]):
        """Detect unusual price movements (50%+ jumps = likely missed splits)."""
        price_history = defaultdict(list)
        
        for trans in sorted(transactions, key=lambda t: t.date):
            if trans.ticker and trans.price > 0:
                price_history[trans.ticker].append((trans.date, trans.price, trans))
        
        for ticker, price_data in price_history.items():
            if len(price_data) < 2:
                continue
            
            for i in range(1, len(price_data)):
                prev_date, prev_price, prev_txn = price_data[i-1]
                curr_date, curr_price, curr_txn = price_data[i]
                
                price_ratio = curr_price / prev_price
                days_diff = (curr_date - prev_date).days
                
                # ENHANCED: Detect 50%+ price jumps (more sensitive)
                if (price_ratio > Decimal("1.5") or price_ratio < Decimal("0.67")) and days_diff < 365:
                    # Calculate if it matches common split ratios
                    likely_split = None
                    common_splits = [
                        (2, 1, "2-for-1"), (3, 1, "3-for-1"), (4, 1, "4-for-1"),
                        (1, 2, "1-for-2 reverse"), (1, 3, "1-for-3 reverse"),
                        (1, 5, "1-for-5 reverse"), (1, 10, "1-for-10 reverse")
                    ]
                    
                    for ratio_to, ratio_from, description in common_splits:
                        # Convert to Decimal for calculation
                        rt = Decimal(ratio_to)
                        rf = Decimal(ratio_from)
                        expected_ratio = rt / rf
                        if abs(price_ratio - (Decimal(1)/expected_ratio)) < Decimal("0.1"):  # Within 10%
                            likely_split = description
                            break
                    
                    split_hint = f" (likely {likely_split} split)" if likely_split else ""
                    
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_WARNING,
                        "Price Jump - Likely Split",
                        f"{ticker}: Price changed from €{prev_price:.2f} to €{curr_price:.2f} " +
                        f"({price_ratio:.2f}x) in {days_diff} days{split_hint}. " +
                        f"ACTION: Check yfinance split history or add to corporate_actions_config.py",
                        curr_txn
                    ))
    
    def detect_likely_missed_splits(self, transactions: List[Transaction]):
        """Detect dramatic price drops with share increases (clear split indicators)."""
        holdings = defaultdict(lambda: {'shares': Decimal(0), 'last_price': None, 'last_date': None})
        
        for trans in sorted(transactions, key=lambda t: t.date):
            if not trans.ticker or trans.price == 0:
                continue
            
            ticker = trans.ticker
            prev_shares = holdings[ticker]['shares']
            prev_price = holdings[ticker]['last_price']
            prev_date = holdings[ticker]['last_date']
            
            if trans.type == TransactionType.BUY:
                holdings[ticker]['shares'] += trans.shares
                holdings[ticker]['last_price'] = trans.price
                holdings[ticker]['last_date'] = trans.date
            elif trans.type == TransactionType.SELL:
                holdings[ticker]['shares'] -= trans.shares
                holdings[ticker]['last_price'] = trans.price
                holdings[ticker]['last_date'] = trans.date
            
            # Check for sudden share count jumps with price drops
            if prev_price and prev_shares > 0:
                share_ratio = (prev_shares + (trans.shares if trans.type == TransactionType.BUY else Decimal(0))) / prev_shares
                price_ratio = trans.price / prev_price
                
                # Share count doubled but price halved = likely 2-for-1 split
                if share_ratio > 1.8 and price_ratio < 0.6:
                    days_diff = (trans.date - prev_date).days if prev_date else 0
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_ERROR,
                        "Missed Split Detected",
                        f"{ticker}: Share count increased {share_ratio:.1f}x while price dropped {price_ratio:.1f}x " +
                        f"(likely stock split not applied). " +
                        f"ACTION: Add split to corporate_actions_config.py between {prev_date.date()} and {trans.date.date()}",
                        trans
                    ))
    
    def detect_orphaned_positions(self, transactions: List[Transaction]):
        """Detect positions that appear without buy orders (spin-offs, transfers)."""
        # Track first transaction of each type per ticker
        first_transactions = {}  # ticker -> first transaction
        holdings_from_buys = defaultdict(Decimal)
        
        for trans in sorted(transactions, key=lambda t: t.date):
            if not trans.ticker:
                continue
            
            ticker = trans.ticker
            
            # Track first transaction
            if ticker not in first_transactions:
                first_transactions[ticker] = trans
            
            # Track shares from buys
            if trans.type == TransactionType.BUY or trans.type == TransactionType.TRANSFER_IN:
                holdings_from_buys[ticker] += trans.shares
            elif trans.type == TransactionType.SELL:
                # Check if we're selling more than we ever bought
                if holdings_from_buys[ticker] == 0:
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_WARNING,
                        "Orphaned Position - Possible Spin-off",
                        f"{ticker}: Selling shares without any buy orders. " +
                        f"This could be a spin-off or transfer from another broker. " +
                        f"ACTION: Add spin-off to corporate_actions_config.py or import transfer transactions",
                        trans
                    ))
                holdings_from_buys[ticker] -= trans.shares
            elif trans.type == TransactionType.DIVIDEND:
                # Dividend on position we never bought
                if holdings_from_buys[ticker] == 0:
                    self.issues.append(ValidationIssue(
                        ValidationIssue.SEVERITY_INFO,
                        "Orphaned Dividend",
                        f"{ticker}: Receiving dividend without buy order. Possible spin-off or missing buy transaction.",
                        trans
                    ))
    
    def check_data_completeness(self, transactions: List[Transaction]):
        """Check for missing required data."""
        missing_ticker = sum(1 for t in transactions if not t.ticker and t.type in [
            TransactionType.BUY, TransactionType.SELL, TransactionType.DIVIDEND
        ])
        
        if missing_ticker > 0:
            self.issues.append(ValidationIssue(
                ValidationIssue.SEVERITY_WARNING,
                "Completeness",
                f"{missing_ticker} transactions missing ticker information",
                None
            ))
        
        missing_name = sum(1 for t in transactions if not t.name and t.ticker)
        if missing_name > 0:
            self.issues.append(ValidationIssue(
                ValidationIssue.SEVERITY_INFO,
                "Completeness",
                f"{missing_name} transactions missing asset name",
                None
            ))
    
    def check_date_order(self, transactions: List[Transaction]):
        """Verify transactions are in reasonable date order."""
        if not transactions:
            return
        
        dates = [t.date for t in transactions]
        min_date = min(dates)
        max_date = max(dates)
        
        # Check for future transactions
        future = [t for t in transactions if t.date.date() > datetime.now().date()]
        if future:
            self.issues.append(ValidationIssue(
                ValidationIssue.SEVERITY_WARNING,
                "Future Date",
                f"{len(future)} transactions dated in the future",
                None
            ))
        
        # Check for very old transactions (might be data error)
        very_old = [t for t in transactions if t.date.date() < (datetime.now() - timedelta(days=365*50)).date()]
        if very_old:
            self.issues.append(ValidationIssue(
                ValidationIssue.SEVERITY_INFO,
                "Old Data",
                f"{len(very_old)} transactions older than 50 years",
                None
            ))
    
    def get_summary(self) -> Dict[str, int]:
        """Get validation summary by severity."""
        summary = {
            "TOTAL": len(self.issues),
            "ERROR": sum(1 for i in self.issues if i.severity == ValidationIssue.SEVERITY_ERROR),
            "WARNING": sum(1 for i in self.issues if i.severity == ValidationIssue.SEVERITY_WARNING),
            "INFO": sum(1 for i in self.issues if i.severity == ValidationIssue.SEVERITY_INFO),
        }
        return summary

    def check_cached_price_history_for_splits(self, transactions: List[Transaction]):
        """
        Check CACHED historical prices for sudden drops (splits).
        
        Uses already-fetched price history from market_cache - no additional API calls!
        Detects splits even if you didn't trade around the split date.
        """
        try:
            from lib.market_cache import get_market_cache
            from datetime import timedelta
            
            cache = get_market_cache()
            
            # Get unique tickers from transactions
            tickers = list({t.ticker for t in transactions if t.ticker})
            
            if not tickers:
                return
            
            # Determine date range from transactions
            sorted_txns = sorted(transactions, key=lambda t: t.date)
            start_date = sorted_txns[0].date.date()
            end_date = sorted_txns[-1].date.date()
            
            # Fetch cached historical prices
            price_df = cache.get_historical_prices(tickers, start_date, end_date)
            
            if price_df.empty:
                logger.debug("No cached price history available for validation")
                return
            
            # Check each ticker for sudden overnight drops
            for ticker in price_df.columns:
                prices = price_df[ticker].dropna()
                
                if len(prices) < 2:
                    continue
                
                for i in range(1, len(prices)):
                    prev_price = prices.iloc[i-1]
                    curr_price = prices.iloc[i]
                    prev_date = prices.index[i-1]
                    curr_date = prices.index[i]
                    
                    # Calculate price change
                    # Convert to Decimal to match comparison literals
                    try:
                        price_ratio = Decimal(str(curr_price)) / Decimal(str(prev_price))
                    except:
                        continue
                    
                    # Check for 40%+ overnight drop (very likely split)
                    if price_ratio < Decimal("0.71") and price_ratio > Decimal("0.45"):  # Between 71% and 45%
                        # Match to common split ratios
                        likely_split = None
                        if abs(price_ratio - Decimal("0.5")) < Decimal("0.05"):  # ~50% drop
                            likely_split = "2-for-1 split"
                        elif abs(price_ratio - Decimal("0.33")) < Decimal("0.05"):  # ~33% drop
                            likely_split = "3-for-1 split"
                        elif abs(price_ratio - Decimal("0.25")) < Decimal("0.05"):  # ~25% drop
                            likely_split = "4-for-1 split"
                        
                        split_hint = f" (likely {likely_split})" if likely_split else ""
                        
                        self.issues.append(ValidationIssue(
                            ValidationIssue.SEVERITY_WARNING,
                            "Historical Split Detected",
                            f"{ticker}: Price dropped from €{prev_price:.2f} to €{curr_price:.2f} " +
                            f"({price_ratio:.1%}) on {curr_date.date()}{split_hint}. " +
                            f"ACTION: Verify split was applied or add to corporate_actions_config.py",
                            None
                        ))
                    
                    # Also check for reverse splits (2x+ price jump overnight)
                    elif price_ratio > Decimal("1.8"):
                        likely_split = None
                        if abs(price_ratio - Decimal("2.0")) < Decimal("0.2"):
                            likely_split = "1-for-2 reverse split"
                        elif abs(price_ratio - Decimal("5.0")) < Decimal("0.5"):
                            likely_split = "1-for-5 reverse split"
                        elif abs(price_ratio - Decimal("10.0")) < Decimal("1.0"):
                            likely_split = "1-for-10 reverse split"
                        
                        split_hint = f" (likely {likely_split})" if likely_split else ""
                        
                        self.issues.append(ValidationIssue(
                            ValidationIssue.SEVERITY_WARNING,
                            "Reverse Split Detected",
                            f"{ticker}: Price jumped from €{prev_price:.2f} to €{curr_price:.2f} " +
                            f"({price_ratio:.1f}x) on {curr_date.date()}{split_hint}. " +
                            f"ACTION: Verify reverse split was applied",
                            None
                        ))
        
        except Exception as e:
            logger.warning(f"Could not check cached price history: {e}")
            # Don't fail validation if cache check fails
