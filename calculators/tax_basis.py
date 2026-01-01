"""
Tax Basis Engine - Universal Lot-Based Cost Tracking

This is the UNIVERSAL engine that works across all jurisdictions. It:
1. Tracks lots (specific purchases)
2. Matches sales to lots using pluggable strategies
3. Outputs standardized TaxEvents

Country-specific tax calculation happens in separate Tax Calculator plugins.

Copyright (c) 2026 Andre. All rights reserved.
"""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

from parsers.enhanced_transaction import Transaction, TransactionType
from calculators.tax_events import TaxLot, TaxEvent, LotMatchingMethod
from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class LotMatchingStrategy(ABC):
    """Abstract base class for lot matching algorithms."""
    
    @abstractmethod
    def match_sell(
        self,
        sell_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxEvent]:
        """
        Match a sell transaction to open lots.
        
        Args:
            sell_transaction: The sell transaction
            open_lots: List of open lots for this ticker
        
        Returns:
            List of TaxEvents (one per lot matched, or single merged event)
        """
        pass
    
    @abstractmethod
    def handle_buy(
        self,
        buy_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxLot]:
        """
        Process a buy transaction.
        
        Args:
            buy_transaction: The buy transaction
            open_lots: Existing open lots for this ticker
        
        Returns:
            Updated list of open lots
        """
        pass
    
    @abstractmethod
    def get_method_name(self) -> LotMatchingMethod:
        """Return the matching method name."""
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
            
            # Calculate proceeds for this portion
            proceeds = (qty_from_lot / sell_transaction.shares) * abs(sell_transaction.total)
            cost_basis = (qty_from_lot / lot.original_quantity) * lot.cost_basis_base
            
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
                sale_fx_rate=sell_transaction.fx_rate
            )
            
            events.append(event)
            
            # Update lot
            lot.quantity -= qty_from_lot
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
            cost_basis_base=abs(buy_transaction.total) * buy_transaction.fx_rate,
            currency_original=buy_transaction.original_currency,
            fees_base=buy_transaction.fees * buy_transaction.fx_rate,
            fx_rate_used=buy_transaction.fx_rate
        )
        
        open_lots.append(new_lot)
        return open_lots
    
    def get_method_name(self) -> LotMatchingMethod:
        return LotMatchingMethod.FIFO


class WeightedAverageStrategy(LotMatchingStrategy):
    """Weighted Average lot matching (Germany/DACH standard)."""
    
    def match_sell(
        self,
        sell_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxEvent]:
        if not open_lots:
            logger.warning(f"No open lots for {sell_transaction.ticker}")
            return []
        
        # Weighted average: Single merged lot
        merged_lot = open_lots[0] if len(open_lots) == 1 else self._merge_lots(open_lots)
        
        qty_to_sell = min(sell_transaction.shares, merged_lot.quantity)
        
        # Calculate proceeds and cost basis
        proceeds = abs(sell_transaction.total)
        cost_basis = (qty_to_sell / merged_lot.quantity) * merged_lot.cost_basis_base
        
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
            cost_basis_base=Decimal(str(cost_basis)),
            realized_gain=Decimal(str(proceeds - cost_basis)),
            holding_period_days=(sell_transaction.date.date() - merged_lot.acquisition_date).days,
            lot_matching_method=LotMatchingMethod.WEIGHTED_AVERAGE,
            lot_ids_used=[merged_lot.lot_id],
            sale_currency=sell_transaction.original_currency,
            sale_fx_rate=sell_transaction.fx_rate,
            notes="Calculated using weighted average cost basis"
        )
        
        # Update merged lot
        merged_lot.quantity -= qty_to_sell
        
        return [event]
    
    def handle_buy(
        self,
        buy_transaction: Transaction,
        open_lots: List[TaxLot]
    ) -> List[TaxLot]:
        # Weighted Average: Merge new purchase with existing lots
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
            cost_basis_base=abs(buy_transaction.total) * buy_transaction.fx_rate,
            currency_original=buy_transaction.original_currency,
            fees_base=buy_transaction.fees * buy_transaction.fx_rate,
            fx_rate_used=buy_transaction.fx_rate
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
        self.realized_events: List[TaxEvent] = []
    
    def _get_asset_key(self, txn: Transaction) -> str:
        """
        Get unique identifier for asset.
        
        Prefers ISIN (globally unique) with ticker fallback.
        Format: "ISIN:{code}" or "TICKER:{symbol}"
        """
        if txn.isin:
            return f"ISIN:{txn.isin}"
        return f"TICKER:{txn.ticker}"
    
    def process_all_transactions(self):
        """Process all transactions and generate tax events."""
        logger.info(f"Processing {len(self.transactions)} transactions with {self.strategy.get_method_name().value}")
        
        for txn in self.transactions:
            self.process_transaction(txn)
        
        logger.info(f"Generated {len(self.realized_events)} tax events")
    
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
