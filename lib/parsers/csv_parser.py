"""CSV parser with automatic format detection and multi-currency support."""

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
from io import StringIO
from typing import List, Dict, Optional, Any
import pandas as pd

# Import enhanced transaction model
from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)


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
        'date': ['datetime', 'datum', 'transaction_date', 'time'],
        'type': ['type', 'typ', 'transaction_type', 'action'],
        'ticker': ['symbol', 'ticker'],
        'isin': ['isin', 'identifier', 'wkn', 'cusip'],
        'name': ['holdingname', 'holding_name', 'security', 'description', 'name'],
        'asset_type': ['asset_type', 'assettype', 'security_type', 'instrument_type'],
        'shares': ['shares', 'quantity', 'units', 'amount'],
        'price': ['price', 'unit_price', 'share_price'],
        'fees': ['fee', 'fees', 'commission'],
        'total': ['total', 'net_amount', 'cash_flow', 'amount'],
        'original_currency': ['originalcurrency', 'currency', 'ccy'],
        'fx_rate': ['fxrate', 'exchange_rate', 'fx', 'rate'],
        'broker': ['broker', 'depot', 'account'],
        'reference_id': ['reference_id', 'transaction_id', 'order_id', 'trade_id'],
        'withholding_tax': ['withholding_tax', 'tax_withheld', 'withheld', 'tax'],
        'realized_gain': ['realizedgains', 'realized_gains', 'realized_gain', 'gain_loss'],
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
            # Positive cash flows
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
        logger.info("=" * 60)
        logger.info("Starting CSV parsing")
        logger.info("=" * 60)
        
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
        
        logger.info(f"Read {len(df)} rows, {len(df.columns)} columns: {list(df.columns)}")
        
        # Strip quotes from column names
        df.columns = df.columns.str.strip().str.strip('"')
        
        # Map columns
        column_map = self.map_columns(df)
        df_mapped = df.rename(columns=column_map)
        
        # Ensure required columns exist
        required = ['date', 'type']
        missing = [col for col in required if col not in df_mapped.columns]
        if missing:
            error_msg = f"Missing required columns: {missing}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Parse transactions
        transactions = []
        errors = []
        error_categories = {
            'invalid_date': 0,
            'unknown_type': 0,
            'missing_ticker': 0,
            'missing_price': 0,
            'general_error': 0
        }
        
        for idx, row in df_mapped.iterrows():
            try:
                # Helper to safely get scalar value from row
                def get_val(key, default=''):
                    """Get scalar value from row, handling Series properly."""
                    val = row.get(key, default)
                    # Handle Series edge case
                    if isinstance(val, pd.Series):
                        return val.iloc[0] if len(val) > 0 else default
                    return val if val is not None else default
                
                # Parse date
                date_val = get_val('date')
                trans_date = self.parse_date(date_val)
                if not trans_date:
                    error = f"Row {idx}: Invalid date '{date_val}'"
                    errors.append(error)
                    error_categories['invalid_date'] += 1
                    logger.warning(error)
                    continue
                
                # Parse type
                type_val = get_val('type')
                trans_type = TransactionType.normalize(type_val)
                if not trans_type:
                    error = f"Row {idx}: Unknown transaction type '{type_val}'"
                    errors.append(error)
                    error_categories['unknown_type'] += 1
                    logger.warning(error)
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

                # Get ISIN (optional)
                isin_val = get_val('isin')
                isin = isin_val if isin_val and isin_val != '' and not pd.isna(isin_val) else None
                
                # Use ticker or ISIN (prefer ISIN if both present)
                if not ticker and isin:
                    ticker = isin
                
                # Log warning if ticker is missing for buy/sell transactions
                if not ticker and trans_type in [TransactionType.BUY, TransactionType.SELL]:
                    error = f"Row {idx}: Missing ticker/ISIN for {trans_type.value} transaction"
                    errors.append(error)
                    error_categories['missing_ticker'] += 1
                    logger.warning(error)

                # Get name (optional)
                name_val = get_val('name')
                name = name_val if name_val and name_val != '' and not pd.isna(name_val) else None
                
                # Log if price is missing for buy/sell
                if price == 0 and trans_type in [TransactionType.BUY, TransactionType.SELL]:
                    error = f"Row {idx}: Missing price for {trans_type.value} transaction (ticker: {ticker})"
                    errors.append(error)
                    error_categories['missing_price'] += 1
                    logger.warning(error)
                
                # Get asset type (optional)
                asset_type_val = get_val('asset_type')
                if asset_type_val and asset_type_val != '' and not pd.isna(asset_type_val):
                    # Use normalize to handle various broker formats
                    asset_type = AssetType.normalize(asset_type_val)
                    if not asset_type:
                        asset_type = AssetType.UNKNOWN
                else:
                    asset_type = AssetType.UNKNOWN  # Will be auto-detected by model
                
                # Get currency
                currency_val = get_val('original_currency', 'EUR')
                currency = currency_val if currency_val != '' else 'EUR'
                
                # Get broker (optional)
                broker_val = get_val('broker')
                broker = broker_val if broker_val and broker_val != '' and not pd.isna(broker_val) else None
                
                # Get reference ID (optional)
                ref_id_val = get_val('reference_id')
                reference_id = ref_id_val if ref_id_val and ref_id_val != '' and not pd.isna(ref_id_val) else None
                
                # Get withholding tax (optional)
                withholding_tax = self.normalize_decimal(get_val('withholding_tax', 0))
                
                # Get realized gain (optional)
                realized_gain = self.normalize_decimal(get_val('realized_gain', 0))
                
                # Create transaction
                transaction = Transaction(
                    date=trans_date,
                    type=trans_type,
                    ticker=ticker,
                    isin=isin,
                    name=name,
                    asset_type=asset_type,
                    shares=shares,
                    price=price,
                    fees=fees,
                    total=total,
                    original_currency=currency,
                    fx_rate=fx_rate,
                    broker=broker,
                    reference_id=reference_id,
                    withholding_tax=withholding_tax,
                    realized_gain=realized_gain,
                )
                
                transactions.append(transaction)
                
            except Exception as e:
                error = f"Row {idx}: {str(e)}"
                errors.append(error)
                error_categories['general_error'] += 1
                logger.error(f"Failed to parse row {idx}: {e}", exc_info=True)
        
        logger.info("=" * 60)
        logger.info(f"CSV Parsing Complete: {len(transactions)} successful, {len(errors)} errors")
        logger.info(f"Error breakdown:")
        for category, count in error_categories.items():
            if count > 0:
                logger.info(f"  - {category}: {count}")
        logger.info("=" * 60)
        
        if errors and len(errors) > 10:
            logger.warning(f"First 10 errors:")
            for i, error in enumerate(errors[:10], 1):
                logger.warning(f"  {i}. {error}")
            logger.warning(f"  ... and {len(errors) - 10} more errors")
        elif errors:
            logger.warning(f"All {len(errors)} errors:")
            for i, error in enumerate(errors, 1):
                logger.warning(f"  {i}. {error}")
        
        return transactions
