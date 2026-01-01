"""
Near-Duplicate Detection with ISIN-Based Matching

Detects potential duplicate transactions using robust ISIN + shares + direction logic.
Distinguishes between duplicates (same direction) and transfers (opposite direction).

Copyright (c) 2026 Andre. All rights reserved.
"""

from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from enum import Enum

from parsers.enhanced_transaction import Transaction, TransactionType
from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class DuplicateGroupType(str, Enum):
    """Type of duplicate group."""
    DUPLICATE = "duplicate"          # Same direction, likely duplicate
    TRANSFER = "transfer"            # Opposite direction, likely transfer
    CORPORATE_ACTION = "corporate_action"  # Potential corporate action


@dataclass
class DuplicateCandidate:
    """Represents a transaction that may be part of a duplicate group."""
    transaction: Transaction
    similarity_score: float
    source_name: str


@dataclass
class DuplicateGroup:
    """Group of potentially duplicate transactions."""
    group_id: str
    group_type: DuplicateGroupType
    candidates: List[DuplicateCandidate]
    representative: Optional[Transaction] = None
    
    def get_highest_score_candidate(self) -> DuplicateCandidate:
        """Get candidate with highest similarity score (most complete data)."""
        return max(self.candidates, key=lambda c: c.similarity_score)


class DuplicateDetector:
    """
    Detects near-duplicate transactions using ISIN-based matching.
    
    Algorithm:
    1. ISIN match (exact) OR ticker match
    2. Shares within 0.1% variance
    3. Date within ±2 days
    4. Direction check (same = duplicate, opposite = transfer)
    """
    
    def __init__(self, date_tolerance_days: int = 2, shares_tolerance_pct: Decimal = Decimal("0.001")):
        self.date_tolerance = date_tolerance_days
        self.shares_tolerance = shares_tolerance_pct
    
    def calculate_similarity(
        self,
        txn_a: Transaction,
        txn_b: Transaction
    ) -> Tuple[float, DuplicateGroupType]:
        """
        Calculate similarity score between two transactions.
        
        Returns:
            Tuple of (similarity_score, group_type)
            - score >= 80: High confidence
            - score 60-79: Review needed
            - group_type: DUPLICATE or TRANSFER
        """
        score = 0.0
        
        # 1. ISIN/Ticker match (50 points - CRITICAL)
        if txn_a.isin and txn_b.isin:
            if txn_a.isin == txn_b.isin:
                score += 50
            else:
                return 0.0, DuplicateGroupType.DUPLICATE  # Different ISIN = not duplicate
        elif txn_a.ticker and txn_b.ticker:
            if txn_a.ticker == txn_b.ticker:
                score += 40  # Ticker match less reliable than ISIN
            else:
                return 0.0, DuplicateGroupType.DUPLICATE
        else:
            return 0.0, DuplicateGroupType.DUPLICATE  # Can't match without identifier
        
        # 2. Shares match (30 points - CRITICAL)
        if txn_a.shares > 0 and txn_b.shares > 0:
            shares_diff = abs(txn_a.shares - txn_b.shares) / max(txn_a.shares, txn_b.shares)
            if shares_diff <= self.shares_tolerance:
                score += 30
            elif shares_diff <= Decimal("0.01"):  # Within 1%
                score += 20
            else:
                score += max(0, 15 - (float(shares_diff) * 100))  # Partial credit
        
        # 3. Date proximity (20 points)
        date_diff = abs((txn_a.date.date() - txn_b.date.date()).days)
        if date_diff == 0:
            score += 20
        elif date_diff <= self.date_tolerance:
            score += 15
        elif date_diff <= 7:
            score += 5
        
        # 4. Determine group type based on direction
        same_direction = self._check_same_direction(txn_a, txn_b)
        
        if same_direction:
            group_type = DuplicateGroupType.DUPLICATE
        else:
            group_type = DuplicateGroupType.TRANSFER
            # Bonus for opposite direction transfers
            if score >= 60:
                logger.info(f"Opposite direction detected: {txn_a.type} vs {txn_b.type} - likely transfer")
        
        return score, group_type
    
    def _check_same_direction(self, txn_a: Transaction, txn_b: Transaction) -> bool:
        """Check if transactions have same direction."""
        buy_types = {TransactionType.BUY, TransactionType.TRANSFER_IN}
        sell_types = {TransactionType.SELL, TransactionType.TRANSFER_OUT}
        
        a_is_buy = txn_a.type in buy_types
        b_is_buy = txn_b.type in buy_types
        
        a_is_sell = txn_a.type in sell_types
        b_is_sell = txn_b.type in sell_types
        
        return (a_is_buy and b_is_buy) or (a_is_sell and b_is_sell)
    
    def find_duplicate_groups(
        self,
        transactions: List[Transaction],
        min_score: float = 60.0
    ) -> List[DuplicateGroup]:
        """
        Find all potential duplicate groups in transaction list.
        
        Args:
            transactions: List of transactions to analyze
            min_score: Minimum similarity score to flag (default 60)
        
        Returns:
            List of DuplicateGroup objects
        """
        groups = []
        processed_indices = set()
        
        for i, txn_a in enumerate(transactions):
            if i in processed_indices:
                continue
            
            # Skip non-tradeable transaction types
            if txn_a.type in [TransactionType.DIVIDEND, TransactionType.INTEREST, TransactionType.FEE]:
                continue
            
            group_candidates = []
            
            for j, txn_b in enumerate(transactions[i+1:], start=i+1):
                if j in processed_indices:
                    continue
                
                # Skip non-tradeable types
                if txn_b.type in [TransactionType.DIVIDEND, TransactionType.INTEREST, TransactionType.FEE]:
                    continue
                
                score, group_type = self.calculate_similarity(txn_a, txn_b)
                
                if score >= min_score:
                    # First match - add both transactions
                    if not group_candidates:
                        group_candidates.append(DuplicateCandidate(
                            transaction=txn_a,
                            similarity_score=score,
                            source_name=txn_a.import_source or "Unknown"
                        ))
                    
                    group_candidates.append(DuplicateCandidate(
                        transaction=txn_b,
                        similarity_score=score,
                        source_name=txn_b.import_source or "Unknown"
                    ))
                    
                    processed_indices.add(j)
            
            if group_candidates:
                processed_indices.add(i)
                
                # Create group
                group = DuplicateGroup(
                    group_id=f"dup_{i}_{datetime.now().timestamp()}",
                    group_type=group_type,
                    candidates=group_candidates
                )
                
                groups.append(group)
                
                logger.info(
                    f"Found {group.group_type.value} group with {len(group_candidates)} candidates "
                    f"(score: {group_candidates[0].similarity_score:.1f})"
                )
        
        return groups


if __name__ == "__main__":
    # Quick test
    detector = DuplicateDetector()
    
    # Test case 1: Same direction (duplicate)
    txn1 = Transaction(
        date=datetime(2024, 1, 15),
        type=TransactionType.BUY,
        ticker="AAPL",
        isin="US0378331005",
        shares=Decimal("10"),
        price=Decimal("150.00"),
        total=Decimal("1500.00"),
        currency="USD"
    )
    
    txn2 = Transaction(
        date=datetime(2024, 1, 15),
        type=TransactionType.BUY,
        ticker="AAPL",
        isin="US0378331005",
        shares=Decimal("10.00"),
        price=Decimal("150.05"),
        total=Decimal("1500.50"),
        currency="USD"
    )
    
    score, group_type = detector.calculate_similarity(txn1, txn2)
    print(f"Same direction test: Score={score:.1f}, Type={group_type.value}")
    print(f"Expected: High score (>=80), Type=duplicate\n")
    
    # Test case 2: Opposite direction (transfer)
    txn3 = Transaction(
        date=datetime(2024, 1, 15),
        type=TransactionType.TRANSFER_OUT,
        ticker="AAPL",
        isin="US0378331005",
        shares=Decimal("10"),
        price=Decimal("0"),
        total=Decimal("0"),
        currency="USD"
    )
    
    txn4 = Transaction(
        date=datetime(2024, 1, 16),
        type=TransactionType.TRANSFER_IN,
        ticker="AAPL",
        isin="US0378331005",
        shares=Decimal("10"),
        price=Decimal("0"),
        total=Decimal("0"),
        currency="USD"
    )
    
    score, group_type = detector.calculate_similarity(txn3, txn4)
    print(f"Opposite direction test: Score={score:.1f}, Type={group_type.value}")
    print(f"Expected: High score (>=80), Type=transfer")
