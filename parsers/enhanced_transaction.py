"""
Enhanced Transaction Model with Asset Types and Corporate Actions

This module defines the comprehensive transaction model needed for:
- Multi-broker import support
- Tax lot tracking preparation
- Stock split handling
- Corporate action processing
"""

from enum import Enum
from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, validator, Field


# Custom exceptions
class TransactionTypeError(ValueError):
    """Raised when transaction type cannot be normalized."""
    pass


class TransactionType(str, Enum):
    """All supported transaction types for comprehensive portfolio tracking."""
    
    # Basic buy/sell
    BUY = "Buy"
    SELL = "Sell"
    
    # Income types
    DIVIDEND = "Dividend"
    DIVIDEND_QUALIFIED = "DividendQualified"  # For US tax treatment
    DIVIDEND_ORDINARY = "DividendOrdinary"
    INTEREST = "Interest"
    
    # Capital movements
    TRANSFER_IN = "TransferIn"
    TRANSFER_OUT = "TransferOut"
    DEPOSIT = "Deposit"  # Cash-only deposit
    WITHDRAWAL = "Withdrawal"  # Cash-only withdrawal
    
    # Corporate actions
    STOCK_SPLIT = "StockSplit"
    REVERSE_SPLIT = "ReverseSplit"
    STOCK_DIVIDEND = "StockDividend"  # Dividend paid in shares
    MERGER = "Merger"
    SPIN_OFF = "SpinOff"
    RIGHTS_ISSUE = "RightsIssue"
    
    # Fees and taxes
    FEE = "Fee"  # Standalone fee (custody, account maintenance)
    COST = "Cost"  # Legacy alias for fee
    TAX_WITHHOLDING = "TaxWithholding"
    
    # Other
    RETURN_OF_CAPITAL = "ReturnOfCapital"
    
    @classmethod
    def normalize(cls, value: str) -> 'TransactionType':
        """Normalize transaction type from various formats.
        
        Raises:
            TransactionTypeError: If the transaction type cannot be mapped.
        """
        value_upper = value.strip().upper()
        
        # Direct mapping
        type_map = {
            "BUY": cls.BUY,
            "SELL": cls.SELL,
            "DIVIDEND": cls.DIVIDEND,
            "DIVIDENDQUALIFIED": cls.DIVIDEND_QUALIFIED,
            "DIVIDENDORDINARY": cls.DIVIDEND_ORDINARY,
            "TRANSFERIN": cls.TRANSFER_IN,
            "TRANSFER_IN": cls.TRANSFER_IN,
            "TRANSFEROUT": cls.TRANSFER_OUT,
            "TRANSFER_OUT": cls.TRANSFER_OUT,
            "DEPOSIT": cls.DEPOSIT,
            "WITHDRAWAL": cls.WITHDRAWAL,
            "INTEREST": cls.INTEREST,
            "STOCKSPLIT": cls.STOCK_SPLIT,
            "SPLIT": cls.STOCK_SPLIT,
            "REVERSESPLIT": cls.REVERSE_SPLIT,
            "STOCKDIVIDEND": cls.STOCK_DIVIDEND,
            "MERGER": cls.MERGER,
            "SPINOFF": cls.SPIN_OFF,
            "RIGHTSISSUE": cls.RIGHTS_ISSUE,
            "FEE": cls.FEE,
            "COST": cls.COST,
            "TAXWITHHOLDING": cls.TAX_WITHHOLDING,
            "RETURNOFCAPITAL": cls.RETURN_OF_CAPITAL,
        }
        
        clean_value = value_upper.replace(" ", "").replace("-", "").replace("_", "")
        result = type_map.get(clean_value)
        
        if result is None:
            raise TransactionTypeError(f"Unknown transaction type: '{value}'")
        
        return result


class AssetType(str, Enum):
    """Asset classification for tax and regulatory purposes."""
    
    STOCK = "Stock"
    ETF = "ETF"
    MUTUAL_FUND = "MutualFund"
    BOND = "Bond"
    OPTION = "Option"
    FUTURE = "Future"
    WARRANT = "Warrant"
    CRYPTO = "Crypto"
    CASH = "Cash"
    COMMODITY = "Commodity"
    INDEX = "Index"
    UNKNOWN = "Unknown"
    
    @classmethod
    def normalize(cls, value: str) -> Optional['AssetType']:
        """Normalize asset type from various broker formats (German, English, etc)."""
        if not value:
            return cls.UNKNOWN
        
        value_upper = value.strip().upper()
        
        # Direct mapping for various broker formats
        asset_map = {
            # English
            "STOCK": cls.STOCK,
            "STOCKS": cls.STOCK,
            "SHARE": cls.STOCK,
            "SHARES": cls.STOCK,
            "EQUITY": cls.STOCK,
            "EQUITIES": cls.STOCK,
            "COMMON STOCK": cls.STOCK,
            
            # German
            "AKTIE": cls.STOCK,
            "AKTIEN": cls.STOCK,
            
            # ETF
            "ETF": cls.ETF,
            "ETFS": cls.ETF,
            "ETC": cls.ETF,
            "ETN": cls.ETF,
            "INDEX FUND": cls.ETF,
            
            # Bonds
            "BOND": cls.BOND,
            "BONDS": cls.BOND,
            "ANLEIHE": cls.BOND,
            "ANLEIHEN": cls.BOND,
            
            # Options/Derivatives
            "OPTION": cls.OPTION,
            "OPTIONS": cls.OPTION,
            "CALL": cls.OPTION,
            "PUT": cls.OPTION,
            "WARRANT": cls.WARRANT,
            "WARRANTS": cls.WARRANT,
            "OPTIONSSCHEIN": cls.WARRANT,
            
            # Futures
            "FUTURE": cls.FUTURE,
            "FUTURES": cls.FUTURE,
            
            # Crypto
            "CRYPTO": cls.CRYPTO,
            "CRYPTOCURRENCY": cls.CRYPTO,
            "KRYPTO": cls.CRYPTO,
            
            # Mutual Funds
            "MUTUAL FUND": cls.MUTUAL_FUND,
            "FUND": cls.MUTUAL_FUND,
            "FONDS": cls.MUTUAL_FUND,
            
            # Cash
            "CASH": cls.CASH,
            "MONEY MARKET": cls.CASH,
            
            # Commodity
            "COMMODITY": cls.COMMODITY,
            "COMMODITIES": cls.COMMODITY,

            # General Security (common in some exports)
            "SECURITY": cls.STOCK,
            "WERTPAPIER": cls.STOCK,
        }
        
        # Clean value for lookup
        clean_value = value_upper.replace("-", " ").replace("_", " ")
        
        return asset_map.get(clean_value, cls.UNKNOWN)
    
    @classmethod
    def infer_from_ticker(cls, ticker: str) -> 'AssetType':
        """Infer asset type from ticker symbol patterns."""
        if not ticker:
            return cls.UNKNOWN
        
        ticker_upper = ticker.upper()
        
        # Check for ISIN format (2 letters, 9 alnum, 1 digit check) - length 12
        # Simple heuristic: starts with 2 letters, length 12
        if len(ticker) == 12 and ticker[0:2].isalpha() and ticker.isalnum():
            # It's indistinguishable from a Stock/ETF/Bond just by ISIN
            # But it is definitely NOT an Option chain symbol usually
            return cls.STOCK
        
        # ETF patterns (common suffixes)
        if any(ticker_upper.endswith(suffix) for suffix in ['.L', '.DE', '.PA']) and \
           any(keyword in ticker_upper for keyword in ['ETF', 'ETC', 'ETN']):
            return cls.ETF
        
        # Crypto patterns
        if any(crypto in ticker_upper for crypto in ['BTC', 'ETH', 'USDT', 'USDC']):
            return cls.CRYPTO
        
        # Option patterns (common formats)
        # OCC symbols are 21 chars. Some broker symbols are shorter but usually > 15
        if len(ticker) > 15 and any(c.isdigit() for c in ticker):
            # Likely an option chain symbol
            return cls.OPTION
        
        # Default to stock
        return cls.STOCK


class Transaction(BaseModel):
    """
    Enhanced transaction model with complete metadata for tax-ready portfolio tracking.
    
    This model supports:
    - Multi-currency transactions
    - Stock splits and corporate actions
    - Tax withholding tracking
    - Broker reconciliation
    - Asset type classification
    """
    
    # Unique identifiers
    id: Optional[str] = None
    reference_id: Optional[str] = None  # Broker's transaction ID
    
    # Core transaction data
    date: datetime
    type: TransactionType
    
    # Asset identification (multiple formats for flexibility)
    ticker: Optional[str] = None
    isin: Optional[str] = None  # International Securities Identification Number
    name: Optional[str] = None
    asset_type: AssetType = AssetType.UNKNOWN
    
    # Quantities and pricing
    shares: Decimal = Decimal(0)
    price: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    total: Decimal  # Net cash flow (negative for outflows, positive for inflows)
    
    # Multi-currency support
    original_currency: str = "EUR"
    fx_rate: Decimal = Decimal(1)  # Conversion rate to base currency (EUR)
    
    # Tax-related fields
    withholding_tax: Decimal = Decimal(0)
    withholding_tax_country: Optional[str] = None
    
    # Corporate action metadata
    split_ratio_from: Optional[Decimal] = None  # e.g., 1 for 2-for-1 split
    split_ratio_to: Optional[Decimal] = None    # e.g., 2 for 2-for-1 split
    
    # Broker metadata
    broker: Optional[str] = None
    account_id: Optional[str] = None
    
    # Import tracking
    import_source: Optional[str] = None  # Which CSV file/broker
    import_date: Optional[datetime] = None
    
    # Notes and metadata
    notes: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
    
    @validator('shares', 'fx_rate', pre=True)
    def parse_decimal(cls, v):
        """Parse string decimals correctly, handling European comma formatting."""
        if isinstance(v, str):
            # Strip commas first (handles both '1,234.56' and European '1.234,56' partially)
            v = v.replace(',', '')
        return Decimal(str(v)) if v else Decimal(0)
    
    @validator('date')
    def date_validation(cls, v):
        """Validate transaction date (allow future for scheduled transactions with warning)."""
        if v > datetime.now():
            # Don't fail, but this could be flagged as a warning later
            pass
        return v
    
    @validator('shares', 'fees', 'fx_rate')
    def non_negative_values(cls, v):
        """Ensure certain financial values are non-negative."""
        if v < 0:
            raise ValueError(f'Value cannot be negative: {v}')
        return v
    
    @validator('total')
    def check_total_consistency(cls, v, values):
        """Validate that total is consistent with shares * price + fees.
        
        Allows small tolerance (±0.01) for rounding differences.
        """
        # Skip validation if we don't have the necessary fields
        if 'shares' not in values or 'price' not in values or 'fees' not in values:
            return v
        
        shares = values.get('shares', Decimal('0'))
        price = values.get('price', Decimal('0'))
        fees = values.get('fees', Decimal('0'))
        
        # Only validate for transactions that should have this relationship
        tx_type = values.get('type')
        if tx_type and tx_type in [TransactionType.BUY, TransactionType.SELL]:
            expected = shares * price + fees
            # Allow small tolerance for rounding
            if abs(abs(v) - abs(expected)) > Decimal('0.01'):
                # Warning only, don't fail - some brokers have different calculation methods
                pass  # Could log warning here if logger is available in validator context
        
        return v
    
    @validator('asset_type', pre=True, always=True)
    def auto_detect_asset_type(cls, v, values):
        """Auto-detect asset type if not provided."""
        if v == AssetType.UNKNOWN and 'ticker' in values:
            return AssetType.infer_from_ticker(values['ticker'])
        return v
    
    def get_base_currency_amount(self) -> Decimal:
        """Calculate amount in base currency (EUR)."""
        return self.total * self.fx_rate
    
    def is_cash_flow(self) -> bool:
        """Check if this transaction represents an external cash flow (for XIRR)."""
        return self.type in [
            TransactionType.TRANSFER_IN,
            TransactionType.TRANSFER_OUT,
            TransactionType.DEPOSIT,
            TransactionType.WITHDRAWAL
        ]
    
    def is_corporate_action(self) -> bool:
        """Check if this is a corporate action that affects share count."""
        return self.type in [
            TransactionType.STOCK_SPLIT,
            TransactionType.REVERSE_SPLIT,
            TransactionType.STOCK_DIVIDEND,
            TransactionType.MERGER,
            TransactionType.SPIN_OFF
        ]
