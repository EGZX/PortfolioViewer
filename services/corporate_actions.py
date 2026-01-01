"""
Corporate Actions Service

Handles detection and application of stock splits and other corporate actions
to ensure accurate cost basis and share count calculations.

Copyright (c) 2026 Andre. All rights reserved.
"""

import yfinance as yf
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import pandas as pd

from parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from utils.logging_config import setup_logger

logger = setup_logger(__name__)



# Blacklist for known erroneous splits from data providers
# Format: ticker -> list of (date_str, ratio) tuples to ignore
SPLIT_BLACKLIST = {
    '1211.HK': [('2025-07-30', 6.0)],
    'CNE100000296': [('2025-07-30', 6.0)],
}

class CorporateAction:
    """Represents a corporate action event."""
    
    def __init__(
        self,
        ticker: str,
        action_date: date,
        action_type: str,  # "StockSplit", "ReverseSplit", "SpinOff", "Merger"
        ratio_from: Decimal,
        ratio_to: Decimal,
        # Spin-off specific
        new_ticker: Optional[str] = None,
        spin_off_ratio: Optional[Decimal] = None,
        cost_basis_allocation: Optional[Decimal] = None,  # % of cost to new ticker
        # Merger specific
        acquiring_ticker: Optional[str] = None,
        cash_in_lieu: Optional[Decimal] = None,
        notes: Optional[str] = None
    ):
        self.ticker = ticker
        self.action_date = action_date
        self.action_type = action_type
        self.ratio_from = ratio_from
        self.ratio_to = ratio_to
        self.adjustment_factor = ratio_to / ratio_from
        
        # Spin-off attributes
        self.new_ticker = new_ticker
        self.spin_off_ratio = spin_off_ratio
        self.cost_basis_allocation = cost_basis_allocation or Decimal("0")
        
        # Merger attributes
        self.acquiring_ticker = acquiring_ticker
        self.cash_in_lieu = cash_in_lieu or Decimal("0")
        
        self.notes = notes
    
    def __repr__(self):
        if self.action_type == "SpinOff":
            return f"CorporateAction({self.ticker} spin-off {self.new_ticker}, {self.spin_off_ratio}, {self.action_date})"
        elif self.action_type == "Merger":
            return f"CorporateAction({self.ticker} → {self.acquiring_ticker}, {self.action_date})"
        else:
            return f"CorporateAction({self.ticker}, {self.action_type}, {self.ratio_from}:{self.ratio_to}, {self.action_date})"


class CorporateActionService:
    """
    Handles detection and application of corporate actions.
    
    Key features:
    - Fetch split history from yfinance
    - Load spin-offs and mergers from configuration
    - Extract corporate actions from imported CSVs (Interactive Brokers, Scalable Capital)
    - Adjust historical transactions for all corporate actions
    - Handle cost basis allocation for spin-offs
    - Maintain audit trail of adjustments
    
    RELIABILITY (multiple sources):
    1. CSV-imported actions (MOST RELIABLE - from broker records)
    2. Manual configuration (RELIABLE - user-defined)
    3. yfinance API (LEAST RELIABLE - auto-detected with blacklist filtering)
    """
    
    @staticmethod
    def fetch_split_history(ticker: str) -> List[CorporateAction]:
        """
        Fetch stock split history from yfinance.
        
        Args:
            ticker: Stock ticker symbol
        
        Returns:
            List of CorporateAction objects (excludes future-dated splits)
        """
        try:
            logger.debug(f"Fetching split history for {ticker}")
            stock = yf.Ticker(ticker)
            splits = stock.splits
            
            if splits.empty:
                logger.debug(f"No splits found for {ticker}")
                return []
            
            # Get today's date to filter out future splits
            from datetime import date
            today = date.today()
            
            actions = []
            future_splits_count = 0
            
            for split_date, ratio in splits.items():
                # Convert to date for comparison
                split_date_obj = split_date.date()
                split_date_str = split_date_obj.strftime('%Y-%m-%d')
                
                # CHECK BLACKLIST
                blacklist = SPLIT_BLACKLIST.get(ticker, [])
                is_blacklisted = False
                for bl_date, bl_ratio in blacklist:
                    if bl_date == split_date_str and abs(ratio - bl_ratio) < 0.1:
                        is_blacklisted = True
                        break
                
                if is_blacklisted:
                    logger.warning(f"Ignoring BLACKLISTED split for {ticker} on {split_date_str} (ratio: {ratio}x)")
                    continue
                
                # Ignore future-dated splits
                # Avoid speculative data from yfinance
                if split_date_obj > today:
                    logger.warning(
                        f"{ticker}: Ignoring future-dated split on {split_date_obj} "
                        f"(ratio: {ratio}x). This is likely erroneous data from yfinance."
                    )
                    future_splits_count += 1
                    continue
                
                # yfinance returns the ratio as a multiplier
                # e.g., 2.0 for a 2-for-1 split, 0.5 for a 1-for-2 reverse split
                
                if ratio > 1:
                    action_type = "StockSplit"
                    # 2-for-1 split: ratio_from=1, ratio_to=2
                    ratio_from = Decimal(1)
                    ratio_to = Decimal(str(ratio))
                else:
                    action_type = "ReverseSplit"
                    # 1-for-2 reverse split: ratio_from=2, ratio_to=1
                    ratio_from = Decimal(str(1/ratio))
                    ratio_to = Decimal(1)
                
                action = CorporateAction(
                    ticker=ticker,
                    action_date=split_date_obj,
                    action_type=action_type,
                    ratio_from=ratio_from,
                    ratio_to=ratio_to
                )
                actions.append(action)
                logger.debug(f"Found split: {action}")
            
            if future_splits_count > 0:
                logger.warning(
                    f"{ticker}: Filtered out {future_splits_count} future-dated split(s). "
                    f"Using only {len(actions)} historical splits."
                )
            
            return actions
            
        except Exception as e:
            logger.error(f"Error fetching split history for {ticker}: {e}")
            return []
    
    @staticmethod
    def adjust_transactions_for_splits(
        transactions: List[Transaction],
        splits: Dict[str, List[CorporateAction]]
    ) -> Tuple[List[Transaction], List[str]]:
        """
        Adjust all transactions for stock splits that occurred after them.
        
        Args:
            transactions: List of transactions
            splits: Dict mapping ticker -> list of CorporateAction
        
        Returns:
            Tuple of (adjusted_transactions, adjustment_log)
        """
        adjusted_transactions = []
        adjustment_log = []
        
        for trans in transactions:
            if not trans.ticker or trans.ticker not in splits:
                adjusted_transactions.append(trans)
                continue
            
            # Find all splits that occurred AFTER this transaction
            ticker_splits = splits[trans.ticker]
            applicable_splits = [
                split for split in ticker_splits
                if split.action_date > trans.date.date()
            ]
            
            if not applicable_splits:
                adjusted_transactions.append(trans)
                continue
            
            # Calculate cumulative adjustment factor
            cumulative_factor = Decimal(1)
            for split in applicable_splits:
                cumulative_factor *= split.adjustment_factor
            
            # Adjust shares and price
            original_shares = trans.shares
            original_price = trans.price
            
            trans.shares = trans.shares * cumulative_factor
            if trans.price != 0:
                trans.price = trans.price / cumulative_factor
            
            # Add note about adjustment
            split_descriptions = [
                f"{s.ratio_from}-for-{s.ratio_to} on {s.action_date}"
                for s in applicable_splits
            ]
            adjustment_note = f"[Split-adjusted: {', '.join(split_descriptions)}]"
            trans.notes = f"{trans.notes or ''} {adjustment_note}".strip()
            
            # Log adjustment
            log_entry = (
                f"{trans.ticker} transaction on {trans.date.date()}: "
                f"Adjusted shares {original_shares} -> {trans.shares}, "
                f"price {original_price} -> {trans.price} "
                f"(factor: {cumulative_factor})"
            )
            adjustment_log.append(log_entry)
            logger.debug(log_entry)
            
            adjusted_transactions.append(trans)
        
        return adjusted_transactions, adjustment_log
    
    @staticmethod
    def detect_and_apply_splits(
        transactions: List[Transaction],
        fetch_splits: bool = True
    ) -> Tuple[List[Transaction], List[str]]:
        """
        Detect splits for all tickers and apply adjustments.
        Uses cache to avoid redundant API calls.
        Parallelized for faster cache warming.
        
        Args:
            transactions: List of transactions
            fetch_splits: Whether to fetch split data from yfinance
        
        Returns:
            Tuple of (adjusted_transactions, adjustment_log)
        """
        from services.market_cache import get_market_cache
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        if not fetch_splits:
            return transactions, []
        
        logger.info("=" * 60)
        logger.info("Starting split detection and adjustment")
        
        # Get unique tickers
        tickers = list({t.ticker for t in transactions if t.ticker})
        
        if not tickers:
            logger.info("No tickers found in transactions")
            return transactions, []
        
        logger.info(f"Checking splits for {len(tickers)} unique tickers")
        
        # Get cache instance
        cache = get_market_cache()
        
        # Fetch split history for each ticker (Parallelized)
        splits_by_ticker = {}
        
        # Helper function for threading
        def fetch_ticker_splits(ticker):
            return ticker, CorporateActionService.get_cached_splits(ticker)

        # Use 4 workers to speed up warm-up without hitting rate limits too hard
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_ticker = {executor.submit(fetch_ticker_splits, t): t for t in tickers}
            
            for future in as_completed(future_to_ticker):
                try:
                    ticker, split_actions = future.result()
                    if split_actions:
                        splits_by_ticker[ticker] = split_actions
                except Exception as e:
                    logger.error(f"Error checking splits for {future_to_ticker[future]}: {e}")

        logger.info(f"Split check complete. Found splits for {len(splits_by_ticker)} tickers.")
        
        if not splits_by_ticker:
            logger.info("No actionable splits found.")
            logger.info("=" * 60)
            return transactions, []
        
        # Apply adjustments
        logger.info(f"Applying split adjustments...")
        adjusted_transactions, adjustment_log = CorporateActionService.adjust_transactions_for_splits(
            transactions,
            splits_by_ticker
        )
        
        logger.info(f"Split adjustment complete: {len(adjustment_log)} transactions adjusted")
        logger.info("=" * 60)
        
        return adjusted_transactions, adjustment_log

    @staticmethod
    def get_cached_splits(ticker: str) -> List[CorporateAction]:
        """
        Get splits for a ticker, checking cache first then API.
        Applies blacklist and future date filtering.
        """
        from parsers.enhanced_transaction import AssetType
        
        # Do not apply splits to Crypto assets
        # Prevents false positives from ticker collisions
        if AssetType.infer_from_ticker(ticker) == AssetType.CRYPTO:
            return []
            
        from services.market_cache import get_market_cache
        cache = get_market_cache()
        
        cached_splits = cache.get_splits(ticker)
        split_actions = []
        today = date.today()
        sentinel_date = date(1900, 1, 1)
        
        if cached_splits:
            # Check for SENTINEL (Negative Cache) indicating no splits exist
            # If we find the sentinel, we return [] immediately without processing
            for split_date, ratio in cached_splits:
                if split_date == sentinel_date:
                    return []

            # Process cached splits
            for split_date, ratio in cached_splits:
                # SPLIT BLACKLIST check
                blacklist = SPLIT_BLACKLIST.get(ticker, [])
                is_blacklisted = False
                split_date_str = split_date.strftime('%Y-%m-%d')
                for bl_date, bl_ratio in blacklist:
                    if bl_date == split_date_str and abs(ratio - bl_ratio) < 0.1:
                        is_blacklisted = True
                        break
                
                if is_blacklisted:
                    continue
                    
                # Filter future dates from cache
                if split_date > today:
                    continue
                    
                if ratio > 1:
                    action = CorporateAction(
                        ticker=ticker,
                        action_date=split_date,
                        action_type="StockSplit",
                        ratio_from=Decimal(1),
                        ratio_to=Decimal(str(ratio))
                    )
                else:
                    action = CorporateAction(
                        ticker=ticker,
                        action_date=split_date,
                        action_type="ReverseSplit",
                        ratio_from=Decimal(str(1/ratio)),
                        ratio_to=Decimal(1)
                    )
                split_actions.append(action)
            return split_actions
            
        else:
            # Fetch from API
            split_history = CorporateActionService.fetch_split_history(ticker)
            if split_history:
                # Cache the splits
                splits_for_cache = [
                    (action.action_date, float(action.adjustment_factor))
                    for action in split_history
                ]
                cache.set_splits(ticker, splits_for_cache)
                return split_history
            else:
                # Cache negative results
                # Use a sentinel record: 1900-01-01 with ratio 1.0 (no effect)
                # Prevents retrying on reload
                cache.set_splits(ticker, [(sentinel_date, 1.0)])
                return []
        
        return []
    
    @staticmethod
    def load_configured_actions() -> Dict[str, List[CorporateAction]]:
        """
        Load manually configured corporate actions (spin-offs, mergers).
        
        Returns:
            Dict mapping ticker -> list of CorporateAction objects
        """
        try:
            from services.corporate_actions_config import CORPORATE_ACTIONS, MERGERS
            
            actions_by_ticker = {}
            
            # Process spin-offs and configured actions
            for ticker, actions_list in CORPORATE_ACTIONS.items():
                ticker_actions = []
                for action_data in actions_list:
                    action_date = datetime.strptime(action_data["date"], "%Y-%m-%d").date()
                    
                    if action_data["type"] == "SpinOff":
                        action = CorporateAction(
                            ticker=ticker,
                            action_date=action_date,
                            action_type="SpinOff",
                            ratio_from=Decimal(1),
                            ratio_to=Decimal(1),  # No share adjustment for parent
                            new_ticker=action_data["new_ticker"],
                            spin_off_ratio=Decimal(str(action_data["spin_off_ratio"])),
                            cost_basis_allocation=Decimal(str(action_data["cost_basis_allocation"])),
                            notes=action_data.get("notes")
                        )
                        ticker_actions.append(action)
                
                if ticker_actions:
                    actions_by_ticker[ticker] = ticker_actions
            
            # Process mergers
            for ticker, merger_list in MERGERS.items():
                for merger_data in merger_list:
                    action_date = datetime.strptime(merger_data["date"], "%Y-%m-%d").date()
                    
                    action = CorporateAction(
                        ticker=ticker,
                        action_date=action_date,
                        action_type="Merger",
                        ratio_from=Decimal(1),
                        ratio_to=Decimal(str(merger_data.get("exchange_ratio", 0))),
                        acquiring_ticker=merger_data["acquiring_ticker"],
                        cash_in_lieu=Decimal(str(merger_data.get("cash_in_lieu", 0))),
                        notes=merger_data.get("notes")
                    )
                    
                    if ticker not in actions_by_ticker:
                        actions_by_ticker[ticker] = []
                    actions_by_ticker[ticker].append(action)
            
            logger.info(f"Loaded {len(actions_by_ticker)} tickers with configured corporate actions")
            return actions_by_ticker
            
        except Exception as e:
            logger.error(f"Error loading corporate actions config: {e}")
            return {}
    
    @staticmethod 
    def apply_spin_off(
        transactions: List[Transaction],
        action: CorporateAction
    ) -> Tuple[List[Transaction], List[str]]:
        """
        Apply spin-off: Create new holdings in spun-off company.
        
        For each holding in parent company on spin-off date:
        1. Reduce parent cost basis by allocation%
        2. Create new transaction for spun-off shares
        
        Args:
            transactions: List of transactions
            action: Spin-off corporate action
        
        Returns:
            Tuple of (updated_transactions, adjustment_log)
        """
        new_transactions = []
        log = []
        
        # Find all BUY transactions for parent ticker before spin-off
        parent_holdings = [
            t for t in transactions
            if t.ticker == action.ticker
            and t.type == TransactionType.BUY
            and t.date.date() < action.action_date
        ]
        
        for holding in parent_holdings:
            # Calculate shares of new company received
            new_shares = holding.shares * action.spin_off_ratio
            
            # Calculate cost basis allocation
            original_cost = holding.cost_basis_eur or holding.total
            allocated_cost = original_cost * action.cost_basis_allocation
            
            # Reduce parent company cost basis
            holding.cost_basis_eur = original_cost - allocated_cost
            if holding.total:
                holding.total = holding.total - allocated_cost
            
            # Create new transaction for spun-off shares
            spinoff_txn = Transaction(
                date=action.action_date,
                type=TransactionType.BUY,
                ticker=action.new_ticker,
                isin=None,  # Will be enriched later
                name=f"{action.new_ticker} (Spin-off from {action.ticker})",
                asset_type=AssetType.STOCK,
                shares=new_shares,
                price=allocated_cost / new_shares if new_shares > 0 else Decimal(0),
                total=allocated_cost,
                fees=Decimal(0),
                currency=holding.currency,
                cost_basis_eur=allocated_cost,
                notes=f"Spin-off from {action.ticker}: {action.notes or ''}"
            )
            new_transactions.append(spinoff_txn)
            
            log_entry = (
                f"Spin-off {action.ticker} → {action.new_ticker}: "
                f"{new_shares} shares @ {allocated_cost / new_shares if new_shares > 0 else 0:.2f}, "
                f"Cost basis: {allocated_cost:.2f}"
            )
            log.append(log_entry)
            logger.info(log_entry)
        
        # Add new spin-off transactions
        transactions.extend(new_transactions)
        
        return transactions, log
    
    @staticmethod
    def detect_and_apply_all_actions(
        transactions: List[Transaction],
        fetch_splits: bool = True
    ) -> Tuple[List[Transaction], List[str]]:
        """
        COMPREHENSIVE corporate actions handler.
        
        Detects and applies ALL corporate actions in correct order:
        1. Stock splits (from yfinance)
        2. Spin-offs (from configuration)
        3. Mergers (from configuration)
        
        Args:
            transactions: List of transactions
            fetch_splits: Whether to fetch split data
        
        Returns:
            Tuple of (adjusted_transactions, complete_log)
        """
        all_logs = []
        
        # Step 1: Apply stock splits
        logger.info("="*60)
        logger.info("CORPORATE ACTIONS: Step 1 - Stock Splits")
        transactions, split_log = CorporateActionService.detect_and_apply_splits(
            transactions,
            fetch_splits=fetch_splits
        )
        all_logs.extend(split_log)
        
        # Step 2: Load and apply configured actions
        logger.info("CORPORATE ACTIONS: Step 2 - Spin-offs & Mergers")
        configured_actions = CorporateActionService.load_configured_actions()
        
        if configured_actions:
            for ticker, actions in configured_actions.items():
                for action in actions:
                    if action.action_type == "SpinOff":
                        transactions, spinoff_log = CorporateActionService.apply_spin_off(
                            transactions,
                            action
                        )
                        all_logs.extend(spinoff_log)
                    
                    elif action.action_type == "Merger":
                        # TODO: Implement merger handling
                        logger.warning(f"Merger handling not yet implemented: {action}")
        
        logger.info(f"CORPORATE ACTIONS: Complete - {len(all_logs)} adjustments")
        logger.info("="*60)
        
        return transactions, all_logs
