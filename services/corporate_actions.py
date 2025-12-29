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
            List of CorporateAction objects
        """
        try:
            logger.info(f"Fetching split history for {ticker}")
            stock = yf.Ticker(ticker)
            splits = stock.splits
            
            if splits.empty:
                logger.info(f"No splits found for {ticker}")
                return []
            
            actions = []
            for split_date, ratio in splits.items():
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
                    action_date=split_date.date(),
                    action_type=action_type,
                    ratio_from=ratio_from,
                    ratio_to=ratio_to
                )
                actions.append(action)
                logger.info(f"Found split: {action}")
            
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
            logger.info(log_entry)
            
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
        
        Args:
            transactions: List of transactions
            fetch_splits: Whether to fetch split data from yfinance
        
        Returns:
            Tuple of (adjusted_transactions, adjustment_log)
        """
        from services.market_cache import get_market_cache
        
        if not fetch_splits:
            return transactions, []
        
        logger.info("=" * 60)
        logger.info("Starting split detection and adjustment")
        logger.info("=" * 60)
        
        # Get unique tickers
        tickers = {t.ticker for t in transactions if t.ticker}
        
        if not tickers:
            logger.info("No tickers found in transactions")
            return transactions, []
        
        logger.info(f"Checking splits for {len(tickers)} unique tickers")
        
        # Get cache instance
        cache = get_market_cache()
        
        # Fetch split history for each ticker
        splits_by_ticker = {}
        cache_hits = 0
        cache_misses = 0
        
        for ticker in tickers:
            # Check cache first
            cached_splits = cache.get_splits(ticker)
            
            if cached_splits:
                cache_hits += 1
                logger.info(f"Cache HIT: {ticker} has {len(cached_splits)} cached splits")
                # Convert back to CorporateAction objects
                split_actions = []
                for split_date, ratio in cached_splits:
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
                
                splits_by_ticker[ticker] = split_actions
            else:
                cache_misses += 1
                logger.info(f"Cache MISS: Fetching splits for {ticker} from API")
                split_history = CorporateActionService.fetch_split_history(ticker)
                if split_history:
                    splits_by_ticker[ticker] = split_history
                    # Cache the splits
                    splits_for_cache = [
                        (action.action_date, float(action.adjustment_factor))
                        for action in split_history
                    ]
                    cache.set_splits(ticker, splits_for_cache)
                    logger.info(f"Cached {len(split_history)} splits for {ticker}")
        
        logger.info(f"Split cache stats: {cache_hits} hits, {cache_misses} misses")
        
        if not splits_by_ticker:
            logger.info("No splits found for any tickers")
            logger.info("=" * 60)
            return transactions, []
        
        # Apply adjustments
        logger.info(f"Applying split adjustments for {len(splits_by_ticker)} tickers")
        adjusted_transactions, adjustment_log = CorporateActionService.adjust_transactions_for_splits(
            transactions,
            splits_by_ticker
        )
        
        logger.info(f"Split adjustment complete: {len(adjustment_log)} transactions adjusted")
        logger.info("=" * 60)
        
        return adjusted_transactions, adjustment_log
