"""
Tax Basis Engine - Universal Lot-Based Cost Tracking

This is the UNIVERSAL engine that works across all jurisdictions. It:
1. Tracks lots (specific purchases)
2. Matches sales to lots using pluggable strategies
3. Outputs standardized TaxEvents

Country-specific tax calculation happens in separate Tax Calculator plugins.

TAX COMPLIANCE:
- Uses official ECB exchange rates (legal requirement)
- Broker FX rates from CSVs are NOT used for tax calculations
- Historical rates cached permanently (immutable)

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import uuid
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

from lib.parsers.enhanced_transaction import Transaction, TransactionType
from modules.tax.tax_events import TaxLot, TaxEvent, LotMatchingMethod
from modules.tax.currency_lot import CurrencyLot
from lib.utils.logging_config import setup_logger
from lib.ecb_rates import get_ecb_rate

logger = setup_logger(__name__)


class LotMatchingStrategy(ABC):
    """Base class for lot matching strategies (stocks AND currencies)."""
    
    @abstractmethod
    def handle_buy(
        self,
        buy_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxLot]:
        """Add a new stock lot from a buy transaction."""
        pass
    
    @abstractmethod
    def match_sell(
        self,
        sell_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxEvent]:
        """Match a stock sell transaction against open lots."""
        pass
    
    @abstractmethod
    def handle_fx_buy(
        self,
        buy_transaction: Transaction,
        currency_lots: List
    ) -> List:
        """Add a new currency lot from FX buy transaction."""
        pass
    
    @abstractmethod
    def match_fx_sell(
        self,
        sell_transaction: Transaction,
        currency_lots: List
    ) -> TaxEvent:
        """Match FX sell transaction against currency lots."""
        pass
    
    @abstractmethod
    def get_method_name(self) -> LotMatchingMethod:
        """Return the matching method enum value."""
        pass


class FIFOStrategy(LotMatchingStrategy):
    """First-In, First-Out lot matching (US/UK standard)."""
    
    def match_sell(
        self,
        sell_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxEvent]:
        # Sort by acquisition date (oldest first)
        sorted_lots = sorted(open_lots, key=lambda x: x.acquisition_date)
        
        remaining_to_sell = sell_transaction.shares
        events = []
        
        for lot in sorted_lots:
            if remaining_to_sell <= 0:
                break
            
            # How much to sell from this lot
            qty_from_lot = min(lot.quantity, remaining_to_sell)
            
            # Calculate proceeds for this portion (proportional to quantity sold)
            proceeds_fraction = qty_from_lot / sell_transaction.shares
            proceeds = proceeds_fraction * abs(sell_transaction.total)
            
            # CRITICAL FIX: Calculate cost basis using CURRENT lot quantity, not original
            # This ensures correct calculation for partially-sold lots
            if lot.quantity > 0:
                fraction_of_lot_sold = qty_from_lot / lot.quantity
                cost_basis = fraction_of_lot_sold * lot.cost_basis_base
            else:
                cost_basis = Decimal(0)
            
            # Create tax event
            event = TaxEvent(
                event_id=f"evt_{sell_transaction.date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
                ticker=sell_transaction.ticker,
                isin=sell_transaction.isin,
                asset_name=sell_transaction.name,
                asset_type=sell_transaction.asset_type.value,
                date_sold=sell_transaction.date.date(),
                date_acquired=lot.acquisition_date,
                quantity_sold=qty_from_lot,
                proceeds_base=Decimal(str(proceeds)),
                cost_basis_base=Decimal(str(cost_basis)),
                realized_gain=Decimal(str(proceeds - cost_basis)),
                holding_period_days=(sell_transaction.date.date() - lot.acquisition_date).days,
                lot_matching_method=LotMatchingMethod.FIFO,
                lot_ids_used=[lot.lot_id],
                sale_currency=sell_transaction.original_currency,
                sale_fx_rate=sell_transaction.fx_rate,
                tax_already_paid=proceeds_fraction * sell_transaction.withholding_tax * sell_transaction.fx_rate
            )
            
            events.append(event)
            
            # Update lot: reduce both quantity AND cost basis proportionally
            lot.quantity -= qty_from_lot
            lot.cost_basis_base -= Decimal(str(cost_basis))
            remaining_to_sell -= qty_from_lot
        
        if remaining_to_sell > 0:
            logger.warning(
                f"Orphaned sell: {sell_transaction.ticker} on {sell_transaction.date.date()} "
                f"- selling {remaining_to_sell} more shares than available"
            )
        
        return events
    
    def handle_buy(
        self,
        buy_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxLot]:
        # FIFO: Just add new lot
        
        # TAX COMPLIANCE: Use ECB official rates, not broker rates
        ecb_fx_rate = get_ecb_rate(
            buy_transaction.date.date(),
            buy_transaction.original_currency,
            "EUR"
        )
        
        new_lot = TaxLot(
            lot_id=str(uuid.uuid4()),
            ticker=buy_transaction.ticker,
            isin=buy_transaction.isin,
            asset_name=buy_transaction.name,
            asset_type=buy_transaction.asset_type.value,
            acquisition_date=buy_transaction.date.date(),
            quantity=buy_transaction.shares,
            original_quantity=buy_transaction.shares,
            cost_basis_local=abs(buy_transaction.total),
            cost_basis_base=abs(buy_transaction.total) * ecb_fx_rate,
            currency_original=buy_transaction.original_currency,
            fees_base=buy_transaction.fees * ecb_fx_rate,
            fx_rate_used=ecb_fx_rate
        )
        
        open_lots.append(new_lot)
        return open_lots
    
    def get_method_name(self) -> LotMatchingMethod:
        return LotMatchingMethod.FIFO
    
    def handle_fx_buy(self, buy_transaction: Transaction, currency_lots: List) -> List:
        """FIFO: Add new currency lot."""
        
        ecb_rate = get_ecb_rate(buy_transaction.date.date(), buy_transaction.original_currency, "EUR")
        
        lot = CurrencyLot(
            lot_id=str(uuid.uuid4()),
            currency=buy_transaction.original_currency,
            amount=abs(buy_transaction.total) - buy_transaction.fees,
            amount_gross=abs(buy_transaction.total),
            amount_net=abs(buy_transaction.total) - buy_transaction.fees,
            fee_amount=buy_transaction.fees,
            fee_currency=buy_transaction.original_currency,
            cost_basis_eur=abs(buy_transaction.total) * ecb_rate,
            acquisition_date=buy_transaction.date.date(),
            ecb_rate_at_purchase=ecb_rate
        )
        
        currency_lots.append(lot)
        logger.debug(f"FIFO FX Buy: {lot.amount_net:.2f} {buy_transaction.original_currency}, cost: €{lot.cost_basis_eur:.2f}")
        return currency_lots
    
    def match_fx_sell(self, sell_transaction: Transaction, currency_lots: List) -> TaxEvent:
        """FIFO: Match FX sell against oldest lots first."""
        currency = sell_transaction.original_currency
        gross_amount = abs(sell_transaction.total)
        fee_amount = sell_transaction.fees
        total_consumed = gross_amount + fee_amount
        
        ecb_rate_sale = get_ecb_rate(sell_transaction.date.date(), currency, "EUR")
        proceeds_eur = gross_amount * ecb_rate_sale
        
        # FIFO: oldest lots first
        remaining = total_consumed
        total_cost_basis = Decimal(0)
        total_fees_from_lots = Decimal(0)
        earliest_date = None
        
        for lot in sorted(currency_lots, key=lambda x: x.acquisition_date):
            if remaining <= 0:
                break
            
            if earliest_date is None:
                earliest_date = lot.acquisition_date
            
            qty_from_lot = min(lot.amount, remaining)
            fraction = qty_from_lot / lot.amount if lot.amount > 0 else Decimal(0)
            
            cost_from_lot = fraction * lot.cost_basis_eur
            fee_from_lot = fraction * lot.fee_amount
            
            total_cost_basis += cost_from_lot
            total_fees_from_lots += fee_from_lot
            
            lot.amount -= qty_from_lot
            lot.cost_basis_eur -= cost_from_lot
            lot.fee_amount -= fee_from_lot
            remaining -= qty_from_lot
        
        if remaining > Decimal("0.01"):
            logger.warning(f"FIFO FX Sell: Insufficient {currency} lots. Needed {total_consumed:.2f}, shortage: {remaining:.2f}")
        
        event = TaxEvent(
            event_id=f"fx_{sell_transaction.date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
            ticker=f"FX_{currency}",
            asset_type="FX",
            date_sold=sell_transaction.date.date(),
            date_acquired=earliest_date or sell_transaction.date.date(),
            quantity_sold=gross_amount,
            proceeds_base=proceeds_eur,
            cost_basis_base=total_cost_basis,
            realized_gain=proceeds_eur - total_cost_basis,
            holding_period_days=(sell_transaction.date.date() - earliest_date).days if earliest_date else 0,
            lot_matching_method=LotMatchingMethod.FIFO,
            sale_fx_rate=ecb_rate_sale,
            notes=json.dumps({
                "fee_amount": float(fee_amount),
                "fee_currency": currency,
                "fees_from_lots": float(total_fees_from_lots),
                "gross_sold": float(gross_amount),
                "net_proceeds": float(proceeds_eur)
            })
        )
        
        logger.debug(f"FIFO FX Sell: {gross_amount:.2f} {currency} → €{proceeds_eur:.2f}, gain: €{event.realized_gain:.2f}")
        return event


class WeightedAverageStrategy(LotMatchingStrategy):
    """Weighted Average lot matching (Germany/DACH standard)."""
    
    def match_sell(
        self,
        sell_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxEvent]:
        if not open_lots:
            logger.debug(f"No open lots for {sell_transaction.ticker}")
            return []
        
        # Weighted average: Single merged lot
        merged_lot = open_lots[0] if len(open_lots) == 1 else self._merge_lots(open_lots)
        
        # Safety check: cannot sell from exhausted lot
        if merged_lot.quantity <= 0:
            logger.error(f"Cannot sell {sell_transaction.ticker}: lot is exhausted")
            return []
        
        qty_to_sell = min(sell_transaction.shares, merged_lot.quantity)
        
        # Calculate proceeds and Cost basis
        proceeds = abs(sell_transaction.total)
        
        # Cost basis portion for this sale (proportional to shares sold)
        cost_basis_portion = (qty_to_sell / merged_lot.quantity) * merged_lot.cost_basis_base
        
        # Create single tax event
        event = TaxEvent(
            event_id=f"evt_{sell_transaction.date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
            ticker=sell_transaction.ticker,
            isin=sell_transaction.isin,
            asset_name=sell_transaction.name,
            asset_type=sell_transaction.asset_type.value,
            date_sold=sell_transaction.date.date(),
            date_acquired=merged_lot.acquisition_date,
            acquisition_date_range=[merged_lot.acquisition_date],  # Could expand this
            quantity_sold=qty_to_sell,
            proceeds_base=Decimal(str(proceeds)),
            cost_basis_base=Decimal(str(cost_basis_portion)),
            realized_gain=Decimal(str(proceeds - cost_basis_portion)),
            holding_period_days=(sell_transaction.date.date() - merged_lot.acquisition_date).days,
            lot_matching_method=LotMatchingMethod.WEIGHTED_AVERAGE,
            lot_ids_used=[merged_lot.lot_id],
            sale_fx_rate=sell_transaction.fx_rate,
            notes="Calculated using weighted average cost basis",
            tax_already_paid=(qty_to_sell / sell_transaction.shares) * sell_transaction.withholding_tax * sell_transaction.fx_rate
        )
        
        # Update merged lot state
        merged_lot.quantity -= qty_to_sell
        merged_lot.cost_basis_base -= cost_basis_portion # Reduce the pool's total cost basis
        
        # CRITICAL FIX: The open lots must be updated to reflect the merged state
        # Clear existing specific lots and replace with the single merged pool lot
        open_lots.clear()
        if not merged_lot.is_exhausted():
            open_lots.append(merged_lot)
        
        return [event]
    
    def handle_buy(
        self,
        buy_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxLot]:
        # Weighted Average: Merge new purchase with existing lots
        
        # TAX COMPLIANCE: Use ECB official rates, not broker rates
        ecb_fx_rate = get_ecb_rate(
            buy_transaction.date.date(),
            buy_transaction.original_currency,
            "EUR"
        )
        
        new_lot = TaxLot(
            lot_id=str(uuid.uuid4()),
            ticker=buy_transaction.ticker,
            isin=buy_transaction.isin,
            asset_name=buy_transaction.name,
            asset_type=buy_transaction.asset_type.value,
            acquisition_date=buy_transaction.date.date(),
            quantity=buy_transaction.shares,
            original_quantity=buy_transaction.shares,
            cost_basis_local=abs(buy_transaction.total),
            cost_basis_base=abs(buy_transaction.total) * ecb_fx_rate,
            currency_original=buy_transaction.original_currency,
            fees_base=buy_transaction.fees * ecb_fx_rate,
            fx_rate_used=ecb_fx_rate
        )
        
        if not open_lots:
            return [new_lot]
        
        # Merge all lots
        all_lots = open_lots + [new_lot]
        merged = self._merge_lots(all_lots)
        
        return [merged]
    
    def _merge_lots(self, lots: List[TaxLot]) -> TaxLot:
        """Merge multiple lots into single weighted average lot."""
        total_quantity = sum(lot.quantity for lot in lots)
        total_cost = sum(lot.cost_basis_base + lot.fees_base for lot in lots)
        
        earliest_date = min(lot.acquisition_date for lot in lots)
        
        return TaxLot(
            lot_id=str(uuid.uuid4()),
            ticker=lots[0].ticker,
            isin=lots[0].isin,
            asset_name=lots[0].asset_name,
            asset_type=lots[0].asset_type,
            acquisition_date=earliest_date,
            quantity=total_quantity,
            original_quantity=total_quantity,
            cost_basis_local=total_cost,  # Simplified
            cost_basis_base=total_cost,
            currency_original="EUR",  # Merged lots are in base currency
            fees_base=Decimal(0),  # Fees already included in cost_basis_base
            fx_rate_used=Decimal(1)
        )
    
    def get_method_name(self) -> LotMatchingMethod:
        return LotMatchingMethod.WEIGHTED_AVERAGE
    
    def handle_fx_buy(self, buy_transaction: Transaction, currency_lots: List) -> List:
        """WeightedAverage: Merge into existing lots or create new."""
        
        ecb_rate = get_ecb_rate(buy_transaction.date.date(), buy_transaction.original_currency, "EUR")
        currency = buy_transaction.original_currency
        
        new_amount = abs(buy_transaction.total) - buy_transaction.fees
        new_cost = abs(buy_transaction.total) * ecb_rate
        new_fees = buy_transaction.fees
        
        # Find existing lots for this currency
        existing_lots = [lot for lot in currency_lots if lot.currency == currency]
        
        if existing_lots:
            # Merge: calculate weighted average
            total_amount = sum(lot.amount for lot in existing_lots) + new_amount
            total_cost = sum(lot.cost_basis_eur for lot in existing_lots) + new_cost
            total_fees = sum(lot.fee_amount for lot in existing_lots) + new_fees
            
            # Remove old lots
            currency_lots[:] = [lot for lot in currency_lots if lot.currency != currency]
            
            # Create merged lot
            merged_lot = CurrencyLot(
                lot_id=str(uuid.uuid4()),
                currency=currency,
                amount=total_amount,
                amount_gross=total_amount,  # Not tracking separate gross for merged
                amount_net=total_amount,
                fee_amount=total_fees,
                fee_currency=currency,
                cost_basis_eur=total_cost,
                acquisition_date=min(lot.acquisition_date for lot in existing_lots),
                ecb_rate_at_purchase=total_cost / total_amount if total_amount > 0 else Decimal(1)
            )
            currency_lots.append(merged_lot)
            logger.debug(f"WeightedAvg FX Buy: Merged {new_amount:.2f} {currency} into {total_amount:.2f}, avg cost: €{total_cost/total_amount:.4f}")
        else:
            # First purchase of this currency
            lot = CurrencyLot(
                lot_id=str(uuid.uuid4()),
                currency=currency,
                amount=new_amount,
                amount_gross=abs(buy_transaction.total),
                amount_net=new_amount,
                fee_amount=new_fees,
                fee_currency=currency,
                cost_basis_eur=new_cost,
                acquisition_date=buy_transaction.date.date(),
                ecb_rate_at_purchase=ecb_rate
            )
            currency_lots.append(lot)
            logger.debug(f"WeightedAvg FX Buy: New {new_amount:.2f} {currency}, cost: €{new_cost:.2f}")
        
        return currency_lots
    
    def match_fx_sell(self, sell_transaction: Transaction, currency_lots: List) -> TaxEvent:
        """WeightedAverage: Sell from merged lot at average cost."""
        currency = sell_transaction.original_currency
        gross_amount = abs(sell_transaction.total)
        fee_amount = sell_transaction.fees
        total_consumed = gross_amount + fee_amount
        
        ecb_rate_sale = get_ecb_rate(sell_transaction.date.date(), currency, "EUR")
        proceeds_eur = gross_amount * ecb_rate_sale
        
        # Find lot for this currency (should be single merged lot)
        currency_lot = next((lot for lot in currency_lots if lot.currency == currency), None)
        
        if not currency_lot or currency_lot.amount == 0:
            logger.warning(f"WeightedAvg FX Sell: No {currency} lots available")
            # Create event with zero cost basis
            earliest_date = sell_transaction.date.date()
            total_cost_basis = Decimal(0)
        else:
            earliest_date = currency_lot.acquisition_date
            
            # Calculate proportional cost
            if currency_lot.amount > 0:
                fraction = min(Decimal(1), total_consumed / currency_lot.amount)
            else:
                fraction = Decimal(0)
            
            total_cost_basis = fraction * currency_lot.cost_basis_eur
            total_fees = fraction * currency_lot.fee_amount
            
            # Reduce lot
            currency_lot.amount -= total_consumed
            currency_lot.cost_basis_eur -= total_cost_basis
            currency_lot.fee_amount -= total_fees
            
            if currency_lot.amount < Decimal("-0.01"):
                logger.warning(f"WeightedAvg FX Sell: Overdraft {currency} lot by {abs(currency_lot.amount):.2f}")
        
        event = TaxEvent(
            event_id=f"fx_{sell_transaction.date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
            ticker=f"FX_{currency}",
            asset_type="FX",
            date_sold=sell_transaction.date.date(),
            date_acquired=earliest_date,
            quantity_sold=gross_amount,
            proceeds_base=proceeds_eur,
            cost_basis_base=total_cost_basis,
            realized_gain=proceeds_eur - total_cost_basis,
            holding_period_days=(sell_transaction.date.date() - earliest_date).days,
            lot_matching_method=LotMatchingMethod.WEIGHTED_AVERAGE,
            sale_fx_rate=ecb_rate_sale,
            notes=json.dumps({
                "fee_amount": float(fee_amount),
                "fee_currency": currency,
                "gross_sold": float(gross_amount),
                "net_proceeds": float(proceeds_eur)
            })
        )
        
        logger.debug(f"WeightedAvg FX Sell: {gross_amount:.2f} {currency} → €{proceeds_eur:.2f}, gain: €{event.realized_gain:.2f}")
        return event


class TaxBasisEngine:
    """
    Universal tax basis tracking engine.
    
    Processes transactions and outputs TaxEvents for country-specific
    tax calculators to consume.
    """
    
    def __init__(
        self,
        transactions: List[Transaction],
        matching_strategy: str = "FIFO"
    ):
        self.transactions = sorted(transactions, key=lambda t: t.date)
        
        # Initialize strategy
        strategies = {
            "FIFO": FIFOStrategy(),
            "WeightedAverage": WeightedAverageStrategy(),
        }
        
        self.strategy = strategies.get(matching_strategy, FIFOStrategy())
        
        # State: Use ISIN as primary key, ticker as fallback
        self.open_lots: Dict[str, List[TaxLot]] = defaultdict(list)
        self.currency_lots: Dict[str, List[CurrencyLot]] = defaultdict(list)  # FX lot tracking
        self.realized_events: List[TaxEvent] = []
    
    def _get_asset_key(self, txn: Transaction) -> str:
        """
        Get unique identifier for asset.
        
        Prefers ISIN (globally unique and stable) with ticker fallback.
        Format: "ISIN:{code}" or "TICKER:{symbol}"
        
        ISINs are used for tax lot tracking because they never change,
        while tickers can change due to corporate actions or exchange moves.
        """
        if txn.isin:
            return f"ISIN:{txn.isin}"
        return f"TICKER:{txn.ticker}"
    
    def process_all_transactions(self):
        """Process all transactions and generate tax events."""
        logger.debug(f"Processing {len(self.transactions)} transactions with {self.strategy.get_method_name().value}")
        
        for txn in self.transactions:
            self.process_transaction(txn)
        
        logger.debug(f"Generated {len(self.realized_events)} tax events")
    
    def process_transaction(self, txn: Transaction):
        """Process a single transaction."""
        asset_key = self._get_asset_key(txn)
        
        if txn.type == TransactionType.BUY:
            self.open_lots[asset_key] = self.strategy.handle_buy(
                txn,
                self.open_lots[asset_key]
            )
        
        elif txn.type == TransactionType.SELL:
            events = self.strategy.match_sell(
                txn,
                self.open_lots[asset_key]
            )
            self.realized_events.extend(events)
            
            # Clean up exhausted lots
            self.open_lots[asset_key] = [
                lot for lot in self.open_lots[asset_key]
                if not lot.is_exhausted()
            ]
        
        elif txn.type in [TransactionType.DIVIDEND, TransactionType.INTEREST]:
            # Handle Income events (Dividends, Interest)
            # These have 0 quantity sold and 0 cost basis
            proceeds = abs(txn.total) * txn.fx_rate
            
            event = TaxEvent(
                event_id=f"inc_{txn.date.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}",
                ticker=txn.ticker,
                isin=txn.isin,
                asset_name=txn.name,
                asset_type=txn.asset_type.value,
                date_sold=txn.date.date(),
                date_acquired=txn.date.date(),
                quantity_sold=Decimal(0),
                proceeds_base=proceeds,
                cost_basis_base=Decimal(0),
                realized_gain=proceeds,
                holding_period_days=0,
                lot_matching_method=LotMatchingMethod.SPECIFIC_ID,
                sale_currency=txn.original_currency,
                sale_fx_rate=txn.fx_rate,
                notes=txn.type.value, # Stores "Dividend" or "Interest"
                tax_already_paid=txn.withholding_tax * txn.fx_rate
            )
            self.realized_events.append(event)
        
        elif txn.type == TransactionType.FX_BUY:
            self._handle_fx_buy(txn)
        
        elif txn.type == TransactionType.FX_SELL:
            self._handle_fx_sell(txn)
        
        elif txn.type == TransactionType.FX_EXCHANGE:
            # Exchange is a combination of sell + buy
            # For now, log as not implemented
            logger.warning(f"FX_EXCHANGE not fully implemented: {txn.date.date()} {txn.original_currency}")
    
    def get_realized_events(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[TaxEvent]:
        """Get realized events, optionally filtered by date."""
        events = self.realized_events
        
        if start_date:
            events = [e for e in events if e.date_sold >= start_date]
        
        if end_date:
            events = [e for e in events if e.date_sold <= end_date]
        
        return events
    
    def get_open_lots(self, ticker: Optional[str] = None) -> List[TaxLot]:
        """Get open lots, optionally filtered by ticker."""
        if ticker:
            return self.open_lots.get(ticker, [])
        
        # Return all open lots
        all_lots = []
        for lots in self.open_lots.values():
            all_lots.extend(lots)
        return all_lots
    
    def _handle_fx_buy(self, txn: Transaction):
        """Record FX buy using configured strategy."""
        self.currency_lots[txn.original_currency] = self.strategy.handle_fx_buy(
            txn,
            self.currency_lots[txn.original_currency]
        )
    
    def _handle_fx_sell(self, txn: Transaction):
        """Record FX sell using configured strategy."""
        event = self.strategy.match_fx_sell(
            txn,
            self.currency_lots[txn.original_currency]
        )
        self.realized_events.append(event)
        
        # Clean up exhausted lots
        self.currency_lots[txn.original_currency] = [
            lot for lot in self.currency_lots[txn.original_currency]
            if not lot.is_exhausted()
        ]
    
    def export_to_json(self, filepath: str):
        """Export realized events to JSON file."""
        import json
        from decimal import Decimal
        
        def decimal_serializer(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            if isinstance(obj, date):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")
        
        events_data = [
            {
                "event_id": e.event_id,
                "ticker": e.ticker,
                "asset_name": e.asset_name,
                "date_sold": e.date_sold,
                "date_acquired": e.date_acquired,
                "quantity": e.quantity_sold,
                "proceeds": e.proceeds_base,
                "cost_basis": e.cost_basis_base,
                "realized_gain": e.realized_gain,
                "holding_period_days": e.holding_period_days,
                "method": e.lot_matching_method.value
            }
            for e in self.realized_events
        ]
        
        with open(filepath, 'w') as f:
            json.dump(events_data, f, indent=2, default=decimal_serializer)
        
        logger.info(f"Exported {len(events_data)} events to {filepath}")
