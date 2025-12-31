"""
Corporate Actions Service

Handles detection and application of stock splits and other corporate actions
to ensure accurate cost basis and share count calculations.
"""

import yfinance as yf
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import pandas as pd

from parsers.enhanced_transaction import Transaction, TransactionType
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
        action_type: str,
        ratio_from: Decimal,
        ratio_to: Decimal
    ):
        self.ticker = ticker
        self.action_date = action_date
        self.action_type = action_type
        self.ratio_from = ratio_from
        self.ratio_to = ratio_to
        self.adjustment_factor = ratio_to / ratio_from
    
    def __repr__(self):
        return f"CorporateAction({self.ticker}, {self.action_type}, {self.ratio_from}:{self.ratio_to}, {self.action_date})"


class CorporateActionService:
    """
    Handles detection and application of corporate actions.
    
    Key features:
    - Fetch split history from yfinance
    - Adjust historical transactions for splits
    - Adjust share counts and prices
    - Maintain audit trail of adjustments
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
                
                # CRITICAL: Ignore future-dated splits
                # These are often incorrect/speculative data from yfinance
                # and would incorrectly adjust historical transactions
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
        
        # CRITICAL: Never apply splits to Crypto assets
        # Mismatched ticker symbols (e.g. BTC vs stock ticker) can cause false positives
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
                # NEGATIVE CACHING: Cache the fact that no splits exist (or fetch failed)
                # Use a sentinel record: 1900-01-01 with ratio 1.0 (no effect)
                # This prevents retrying failed lookups on every reload (saving ~40s)
                cache.set_splits(ticker, [(sentinel_date, 1.0)])
                return []
        
        return []
