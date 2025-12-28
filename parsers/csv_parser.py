"""CSV parser with automatic format detection and multi-currency support."""

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
from enum import Enum
from io import StringIO
from typing import List, Dict, Optional, Any
import pandas as pd
from pydantic import BaseModel, validator, Field

from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class TransactionType(str, Enum):
    """Supported transaction types."""
    BUY = "Buy"
    SELL = "Sell"
    DIVIDEND = "Dividend"
    TRANSFER_IN = "TransferIn"
    TRANSFER_OUT = "TransferOut"
    INTEREST = "Interest"
    COST = "cost"  # Fee/cost transactions
    
    @classmethod
    def normalize(cls, value: str) -> Optional['TransactionType']:
        """Normalize transaction type from various formats."""
        value_upper = value.strip().upper()
        
        # Direct mapping
        type_map = {
            "BUY": cls.BUY,
            "SELL": cls.SELL,
            "DIVIDEND": cls.DIVIDEND,
            "TRANSFERIN": cls.TRANSFER_IN,
            "TRANSFER_IN": cls.TRANSFER_IN,
            "TRANSFEROUT": cls.TRANSFER_OUT,
            "TRANSFER_OUT": cls.TRANSFER_OUT,
            "INTEREST": cls.INTEREST,
            "COST": cls.COST,
        }
        
        return type_map.get(value_upper.replace(" ", "").replace("-", ""))


class Transaction(BaseModel):
    """
    Represents a single parsed transaction.
    Validated using Pydantic.
    """
    date: datetime
    type: TransactionType
    ticker: Optional[str] = None
    name: Optional[str] = None  # Added name field
    shares: Decimal
    price: Decimal
    fees: Decimal
    total: Decimal
    original_currency: str = "EUR"
    fx_rate: Decimal = Decimal(1)
    broker: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @validator('shares', pre=True)
    def parse_shares(cls, v):
        if isinstance(v, str):
            v = v.replace(',', '.')
        return Decimal(v)
    
    @validator('date')
    def date_not_future(cls, v):
        """Ensure transaction date is not in the future."""
        if v > datetime.now():
            raise ValueError(f'Transaction date cannot be in the future: {v}')
        return v
    
    @validator('shares', 'fees', 'fx_rate')
    def non_negative_financial(cls, v):
        """Ensure financial values are non-negative."""
        if v < 0:
            raise ValueError(f'Financial value cannot be negative: {v}')
        return v


class CSVParser:
    """
    Flexible CSV parser with automatic format detection.
    
    Handles:
    - Multiple delimiters (;, ,, |)
    - Decimal separators (. or ,)
    - Column name variations (fuzzy matching)
    - Missing columns (with defaults)
    - Multi-currency transactions
    """
    
    # Column mapping templates
    COLUMN_MAPPINGS = {
        'date': ['datetime', 'datum', 'transaction_date'],
        'type': ['type', 'typ', 'transaction_type', 'action'],
        'ticker': ['identifier', 'isin', 'wkn', 'symbol', 'ticker'],
        'name': ['holdingname', 'holding_name', 'security', 'description', 'name'],
        'shares': ['shares', 'quantity', 'units'],
        'price': ['price', 'unit_price', 'share_price'],
        'fees': ['fee', 'fees', 'commission'],
        'total': ['amount', 'total', 'net_amount', 'cash_flow'],
        'original_currency': ['originalcurrency', 'currency', 'ccy'],
        'fx_rate': ['fxrate', 'exchange_rate', 'fx', 'rate'],
        'broker': ['broker', 'depot', 'account'],
    }
    
    def __init__(self):
        self.delimiter = None
        self.decimal_separator = None
    
    def detect_delimiter(self, content: str) -> str:
        """Detect CSV delimiter from content."""
        # Check first line
        first_line = content.split('\n')[0] if content else ''
        
        # Count delimiters in first line
        semicolon_count = first_line.count(';')
        comma_count = first_line.count(',')
        
        # Semicolon is more common in first line = German CSV
        if semicolon_count > comma_count:
            return ';'
        
        # Fallback to csv.Sniffer
        sniffer = csv.Sniffer()
        try:
            sample = '\n'.join(content.split('\n')[:5])
            dialect = sniffer.sniff(sample, delimiters=";,|\t")
            return dialect.delimiter
        except Exception:
            # Default to semicolon (German CSV)
            return ';'
    
    def detect_decimal_separator(self, content: str) -> str:
        """Detect decimal separator (. or ,)."""
        # Look for patterns like 123,45 or 123.45
        if ',45' in content or ',99' in content or ',00' in content:
            return ','
        return '.'
    
    def fuzzy_match_column(self, column_name: str, templates: List[str]) -> float:
        """
        Return the best match score for a column against templates.
        Returns: 0.0 to 1.0
        """
        column_lower = column_name.lower().strip()
        
        # Exact match check first
        if column_lower in templates:
            return 1.0
            
        # Fuzzy match score
        best_score = 0.0
        matches = get_close_matches(column_lower, templates, n=1, cutoff=0.7)
        if matches:
            # Calculate similarity ratio
            from difflib import SequenceMatcher
            best_score = SequenceMatcher(None, column_lower, matches[0]).ratio()
            
        return best_score
    
    def map_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """
        Map actual column names to standardized names using a global best-match strategy.
        Ensures that the best fitting column is chosen for each field, avoiding greedy mismatching.
        """
        column_map = {}
        df_columns = list(df.columns)
        assigned_columns = set()
        
        # Calculate all match scores
        # Structure: matches[std_name] = [(score, col_name), ...]
        matches = {}
        
        for std_name, templates in self.COLUMN_MAPPINGS.items():
            col_scores = []
            for col in df_columns:
                score = self.fuzzy_match_column(col, templates)
                if score >= 0.8:  # Strict cutoff
                    col_scores.append((score, col))
            
            # Sort by score descending
            col_scores.sort(key=lambda x: x[0], reverse=True)
            matches[std_name] = col_scores
            
        # Assign columns - prioritize higher scores
        # We process matches greedily by score, but considering the specific field needs
        for std_name, col_scores in matches.items():
            for score, col in col_scores:
                if col not in assigned_columns:
                    column_map[col] = std_name
                    assigned_columns.add(col)
                    logger.info(f"Mapped '{col}' to '{std_name}' (score: {score:.2f})")
                    break
        
        # Special check: Ensure 'ticker' is mapped
        if 'ticker' not in column_map.values() and 'identifier' in df_columns:
             # Fallback: force identifier if available
             column_map['identifier'] = 'ticker'
             logger.info("Forced mapping 'identifier' to 'ticker' as fallback")

        logger.info(f"Final Column mapping: {column_map}")
        return column_map
    
    def normalize_decimal(self, value: Any) -> Decimal:
        """Convert string to Decimal, handling different formats."""
        if pd.isna(value) or value == '':
            return Decimal(0)
        
        try:
            # Convert to string
            val_str = str(value).strip()
            
            # Handle German format: 1.234,56 -> 1234.56
            if self.decimal_separator == ',':
                val_str = val_str.replace('.', '')  # Remove thousand separator
                val_str = val_str.replace(',', '.')  # Convert decimal separator
            
            return Decimal(val_str)
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Could not parse decimal: {value}, error: {e}")
            return Decimal(0)
    
    def parse_date(self, value: Any) -> Optional[datetime]:
        """Parse date from various formats."""
        if pd.isna(value) or value == '':
            return None
        
        date_formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO 8601 with milliseconds
            '%Y-%m-%dT%H:%M:%SZ',      # ISO 8601
            '%Y-%m-%d',                 # ISO date
            '%d.%m.%Y',                 # German format
            '%m/%d/%Y',                 # US format
            '%d/%m/%Y',                 # European format
        ]
        
        val_str = str(value).strip()
        
        for fmt in date_formats:
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                continue
        
        logger.warning(f"Could not parse date: {value}")
        return None
    
    def calculate_total(self, row: pd.Series, transaction_type: TransactionType) -> Decimal:
        """Calculate total amount if missing."""
        shares = row.get('shares', Decimal(0))
        price = row.get('price', Decimal(0))
        fees = row.get('fees', Decimal(0))
        
        if transaction_type == TransactionType.BUY:
            # Buys are negative cash flows
            return -(shares * price + fees)
        elif transaction_type == TransactionType.SELL:
            # Sells are positive cash flows
            return shares * price - fees
        else:
            # Dividends, interest: use amount as-is (positive)
            return shares * price
    
    def parse_csv(self, file_content: str) -> List[Transaction]:
        """
        Parse CSV content into validated Transaction objects.
        
        Args:
            file_content: Raw CSV content as string
        
        Returns:
            List of validated Transaction objects
        
        Raises:
            ValueError: If CSV is malformed or required columns are missing
        """
        # Detect format
        self.delimiter = self.detect_delimiter(file_content)
        self.decimal_separator = self.detect_decimal_separator(file_content)
        
        logger.info(f"Detected delimiter: '{self.delimiter}', decimal: '{self.decimal_separator}'")
        
        # Read CSV
        df = pd.read_csv(
            StringIO(file_content),
            delimiter=self.delimiter,
            quotechar='"',  # Handle quoted fields
            dtype=str,  # Read everything as string initially
            keep_default_na=False,
            on_bad_lines='warn'  # Continue on bad lines
        )
        
        logger.info(f"Read {len(df)} rows, {len(df.columns)} columns")
        
        # Strip quotes from column names
        df.columns = df.columns.str.strip().str.strip('"')
        
        # Map columns
        column_map = self.map_columns(df)
        df_mapped = df.rename(columns=column_map)
        
        # Ensure required columns exist
        required = ['date', 'type']
        missing = [col for col in required if col not in df_mapped.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Parse transactions
        transactions = []
        errors = []
        
        for idx, row in df_mapped.iterrows():
            try:
                # Helper to safely get scalar value from row
                def get_val(key, default=''):
                    """Get scalar value from row, handling Series properly."""
                    val = row.get(key, default)
                    # If it's a Series (shouldn't happen but protect anyway), take first value
                    if isinstance(val, pd.Series):
                        return val.iloc[0] if len(val) > 0 else default
                    return val if val is not None else default
                
                # Parse date
                date_val = get_val('date')
                trans_date = self.parse_date(date_val)
                if not trans_date:
                    errors.append(f"Row {idx}: Invalid date '{date_val}'")
                    continue
                
                # Parse type
                type_val = get_val('type')
                trans_type = TransactionType.normalize(type_val)
                if not trans_type:
                    errors.append(f"Row {idx}: Unknown transaction type '{type_val}'")
                    continue
                
                # Parse amounts
                shares = self.normalize_decimal(get_val('shares', 0))
                price = self.normalize_decimal(get_val('price', 0))
                fees = self.normalize_decimal(get_val('fees', 0))
                fx_rate = self.normalize_decimal(get_val('fx_rate', 1))
                if fx_rate == 0:
                    fx_rate = Decimal(1)
                
                # Get or calculate total
                total_val = get_val('total')
                if total_val == '' or pd.isna(total_val):
                    total = self.calculate_total(
                        {'shares': shares, 'price': price, 'fees': fees},
                        trans_type
                    )
                else:
                    total = self.normalize_decimal(total_val)

                # Enforce sign convention based on type
                if trans_type == TransactionType.BUY:
                    if total > 0:
                        total = -total
                elif trans_type == TransactionType.SELL:
                    if total < 0:
                        total = abs(total)
                elif trans_type == TransactionType.COST:
                    if total > 0:
                        total = -total
                
                # Get ticker (optional)
                ticker_val = get_val('ticker')
                ticker = ticker_val if ticker_val and ticker_val != '' and not pd.isna(ticker_val) else None

                # Get name (optional)
                name_val = get_val('name')
                name = name_val if name_val and name_val != '' and not pd.isna(name_val) else None
                
                # Get currency
                currency_val = get_val('original_currency', 'EUR')
                currency = currency_val if currency_val != '' else 'EUR'
                
                # Get broker (optional)
                broker_val = get_val('broker')
                broker = broker_val if broker_val and broker_val != '' and not pd.isna(broker_val) else None
                
                # Create transaction
                transaction = Transaction(
                    date=trans_date,
                    type=trans_type,
                    ticker=ticker,
                    name=name,
                    shares=shares,
                    price=price,
                    fees=fees,
                    total=total,
                    original_currency=currency,
                    fx_rate=fx_rate,
                    broker=broker,
                )
                
                transactions.append(transaction)
                
            except Exception as e:
                errors.append(f"Row {idx}: {str(e)}")
                logger.warning(f"Failed to parse row {idx}: {e}")
        
        logger.info(f"Successfully parsed {len(transactions)} transactions, {len(errors)} errors")
        
        if errors and len(errors) > 10:
            logger.warning(f"First 10 errors: {errors[:10]}")
        
        return transactions
