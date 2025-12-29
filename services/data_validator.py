"""
Data Quality Validation Service

Provides comprehensive validation and quality checks for imported transaction data
to ensure accuracy and detect common issues.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple
from collections import defaultdict

from parsers.enhanced_transaction import Transaction, TransactionType
from utils.logging_config import setup_logger

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
        """Detect unusual price movements."""
        price_history = defaultdict(list)
        
        for trans in sorted(transactions, key=lambda t: t.date):
            if trans.ticker and trans.price > 0:
                price_history[trans.ticker].append((trans.date, trans.price))
        
        for ticker, prices in price_history.items():
            if len(prices) < 2:
                continue
            
            for i in range(1, len(prices)):
                prev_date, prev_price = prices[i-1]
                curr_date, curr_price = prices[i]
                
                # Check for 10x price jumps (might indicate split not detected)
                if curr_price > prev_price * 5 or curr_price < prev_price / 5:
                    days_diff = (curr_date - prev_date).days
                    if days_diff < 180:  # Within 6 months
                        self.issues.append(ValidationIssue(
                            ValidationIssue.SEVERITY_WARNING,
                            "Price Anomaly",
                            f"{ticker}: Price changed from {prev_price} to {curr_price} " +
                            f"({curr_price/prev_price:.1f}x) in {days_diff} days - possible undetected split?",
                            None
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
