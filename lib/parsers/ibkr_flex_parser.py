
import csv
from decimal import Decimal
from io import StringIO
from typing import List
import pandas as pd
from datetime import datetime

from lib.parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)

class IbkrFlexParser:
    """
    Parser for Interactive Brokers Flex Query CSV exports.
    Handles files with multiple sections/headers (Trades and Cash Transactions).
    """
    
    def parse(self, file_content: str) -> List[Transaction]:
        transactions = []
        
        # Split content into lines
        lines = file_content.strip().splitlines()
        
        # Identify sections
        trade_header_idx = -1
        cash_header_idx = -1
        
        for i, line in enumerate(lines):
            line = line.strip()
            if '"TransactionType"' in line and '"Symbol"' in line:
                trade_header_idx = i
            elif '"Amount"' in line and '"Type"' in line and '"TransactionType"' not in line:
                cash_header_idx = i
                
        # Parse Trades
        if trade_header_idx != -1:
            trade_lines = []
            trade_lines.append(lines[trade_header_idx])
            # Capture lines until next header or empty line
            for i in range(trade_header_idx + 1, len(lines)):
                if i == cash_header_idx:
                    break
                if lines[i].strip():
                    trade_lines.append(lines[i])
                    
            transactions.extend(self._parse_trades(trade_lines))
            
        # Parse Cash
        if cash_header_idx != -1:
            cash_lines = []
            cash_lines.append(lines[cash_header_idx])
            for i in range(cash_header_idx + 1, len(lines)):
                if lines[i].strip():
                    cash_lines.append(lines[i])
                    
            transactions.extend(self._parse_cash(cash_lines))
            
        return transactions

    def _parse_trades(self, lines: List[str]) -> List[Transaction]:
        if not lines:
            return []
            
        transactions = []
        csv_content = '\n'.join(lines)
        df = pd.read_csv(StringIO(csv_content), quotechar='"', dtype=str, keep_default_na=False)
        
        for _, row in df.iterrows():
            try:
                # Filter out Order records, keep Executions
                if 'LevelOfDetail' in row and row['LevelOfDetail'] != 'EXECUTION':
                    continue

                date_str = row.get('DateTime', '').split(';')[0] # '20251210;110104' -> '20251210'
                if not date_str:
                     date_str = row.get('Date/Time', '').split(';')[0]
                
                # Format is YYYYMMDD usually
                try:
                    date = datetime.strptime(date_str, '%Y%m%d')
                except ValueError:
                    # Try alternate format
                    try:
                        date = datetime.strptime(date_str, '%Y-%m-%d') 
                    except ValueError:
                        continue

                trans_type_raw = row.get('TransactionType', '')
                # "ExchTrade" is standard for trades
                
                quant = Decimal(row.get('Quantity', '0').replace(',', ''))
                price = Decimal(row.get('TradePrice', '0').replace(',', ''))
                fees = abs(Decimal(row.get('IBCommission', '0').replace(',', '')))
                
                # Logic to determine BUY/SELL based on Quantity
                # IBKR: Positive Quantity = Buy, Negative = Sell
                if quant > 0:
                    trans_type = TransactionType.BUY
                    total = -(quant * price) - fees
                else:
                    trans_type = TransactionType.SELL
                    total = (abs(quant) * price) - fees
                    quant = abs(quant)

                ticker = row.get('Symbol')
                isin = row.get('ISIN')
                name = row.get('Description')
                
                currency = row.get('CurrencyPrimary', 'EUR') # Or 'Currency'
                
                t = Transaction(
                    date=date,
                    type=trans_type,
                    ticker=ticker,
                    isin=isin,
                    name=name,
                    shares=quant,
                    price=price,
                    fees=fees,
                    total=total,
                    original_currency=currency,
                    broker='interactive_brokers'
                )
                transactions.append(t)
            except Exception as e:
                logger.error(f"Error parsing IBKR trade row: {e}")
                
        return transactions

    def _parse_cash(self, lines: List[str]) -> List[Transaction]:
        if not lines:
            return []
            
        transactions = []
        csv_content = '\n'.join(lines)
        df = pd.read_csv(StringIO(csv_content), quotechar='"', dtype=str, keep_default_na=False)
        
        for _, row in df.iterrows():
            try:
                type_raw = row.get('Type', '')
                if type_raw != 'Deposits/Withdrawals':
                    continue
                    
                date_str = row.get('Date/Time', '')
                if not date_str: 
                    continue
                try:
                    date = datetime.strptime(date_str, '%Y%m%d')
                except ValueError:
                    date = datetime.strptime(date_str, '%Y-%m-%d') 
                    
                amount = Decimal(row.get('Amount', '0').replace(',', ''))
                currency = row.get('CurrencyPrimary', 'EUR')
                
                if amount > 0:
                    trans_type = TransactionType.TRANSFER_IN
                else:
                    trans_type = TransactionType.TRANSFER_OUT
                    
                t = Transaction(
                    date=date,
                    type=trans_type,
                    ticker='CASH', 
                    name=f"Cash {trans_type.value}",
                    shares=Decimal(0),
                    price=Decimal(1),
                    total=amount,
                    original_currency=currency,
                    broker='interactive_brokers'
                )
                transactions.append(t)
            except Exception as e:
                logger.error(f"Error parsing IBKR cash row: {e}")
                
        return transactions
