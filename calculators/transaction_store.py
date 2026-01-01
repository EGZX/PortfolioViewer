"""
Encrypted Transaction Store

Provides persistent storage for transactions from multiple sources with:
- SQLite database backend
- AES-256 encryption for sensitive data (via Fernet)
- Automatic deduplication
- Source management
- Import history tracking

Security:
- All transaction data is encrypted at rest
- Encryption key loaded from Streamlit secrets
- Individual fields encrypted separately for query capability

Copyright (c) 2026 Andre. All rights reserved.
"""

import sqlite3
import hashlib
import json
from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional, Dict, Tuple
from pathlib import Path
from dataclasses import asdict

import streamlit as st
from cryptography.fernet import Fernet
import base64

from parsers.enhanced_transaction import Transaction, TransactionType, AssetType
from calculators.tax_events import ImportResult, DuplicateWarning
from utils.logging_config import setup_logger

logger = setup_logger(__name__)


class EncryptionManager:
    """Manages encryption/decryption for sensitive data."""
    
    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryption manager.
        
        Args:
            key: Base64-encoded Fernet key from secrets, or None to load from st.secrets
        """
        if key is None:
            # Load from Streamlit secrets
            try:
                key = st.secrets["passwords"]["TRANSACTION_STORE_ENCRYPTION_KEY"]
            except (KeyError, FileNotFoundError):
                logger.warning("Encryption key not found in secrets, generating new one")
                # Generate new key (should be saved to secrets!)
                key = Fernet.generate_key().decode()
                logger.warning(f"SAVE THIS KEY TO secrets.toml: {key}")
        
        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()
        
        self.cipher = Fernet(key)
    
    def encrypt(self, data: str) -> str:
        """Encrypt string data, return base64 encoded cipher text."""
        if data is None:
            return None
        encrypted = self.cipher.encrypt(data.encode())
        return base64.b64encode(encrypted).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt base64 encoded cipher text, return original string."""
        if encrypted_data is None:
            return None
        decoded = base64.b64decode(encrypted_data.encode())
        decrypted = self.cipher.decrypt(decoded)
        return decrypted.decode()
    
    def encrypt_decimal(self, value: Decimal) -> str:
        """Encrypt Decimal value."""
        if value is None:
            return None
        return self.encrypt(str(value))
    
    def decrypt_decimal(self, encrypted: str) -> Decimal:
        """Decrypt to Decimal value."""
        if encrypted is None:
            return None
        return Decimal(self.decrypt(encrypted))


class TransactionStore:
    """
    Persistent encrypted storage for transactions from multiple sources.
    
    Features:
    - Multi-source transaction management
    - Automatic deduplication (hash-based)
    - Encrypted sensitive data (prices, amounts, shares)
    - Import history tracking
    - Source-based filtering and deletion
    """
    
    # Fields that should be encrypted (sensitive financial data)
    ENCRYPTED_FIELDS = {
        'shares', 'price', 'total', 'fees',
        'cost_basis_local', 'cost_basis_eur', 'fx_rate'
    }
    
    def __init__(self, db_path: str = "data/transactions.db", encryption_key: Optional[str] = None):
        """
        Initialize transaction store.
        
        Args:
            db_path: Path to SQLite database file
            encryption_key: Optional encryption key (loads from secrets if None)
        """
        self.db_path = db_path
        self.encryption = EncryptionManager(encryption_key)
        
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._init_database()
        
        logger.info(f"TransactionStore initialized (encrypted): {db_path}")
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """Create database tables if they don't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    date TIMESTAMP NOT NULL,
                    type TEXT NOT NULL,
                    
                    -- Asset identification (not encrypted - needed for queries)
                    ticker TEXT,
                    isin TEXT,
                    name TEXT,
                    asset_type TEXT,
                    
                    -- Financial data (ENCRYPTED)
                    shares_enc TEXT,
                    price_enc TEXT,
                    total_enc TEXT,
                    fees_enc TEXT,
                    cost_basis_local_enc TEXT,
                    cost_basis_eur_enc TEXT,
                    fx_rate_enc TEXT,
                    
                    -- Currencies (not encrypted)
                    currency TEXT,
                    original_currency TEXT,
                    
                    -- Source tracking
                    source_name TEXT NOT NULL,
                    source_import_date TIMESTAMP NOT NULL,
                    source_file_hash TEXT,
                    
                    -- Deduplication
                    transaction_hash TEXT UNIQUE,
                    duplicate_of TEXT,
                    
                    -- Metadata
                    broker TEXT,
                    notes TEXT
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON transactions(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker ON transactions(ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_isin ON transactions(isin)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON transactions(source_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON transactions(transaction_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON transactions(type)")
            
            # Import history table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS import_history (
                    import_id TEXT PRIMARY KEY,
                    import_date TIMESTAMP NOT NULL,
                    source_name TEXT NOT NULL,
                    file_name TEXT,
                    file_hash TEXT,
                    transactions_added INTEGER,
                    transactions_skipped INTEGER,
                    transactions_flagged INTEGER,
                    status TEXT,
                    error_log TEXT
                )
            """)
            
            # Duplicate detection tables (near-duplicate tracking)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS duplicate_groups (
                    group_id TEXT PRIMARY KEY,
                    group_type TEXT CHECK(group_type IN ('duplicate', 'transfer', 'corporate_action')),
                    resolution_status TEXT CHECK(resolution_status IN ('pending', 'resolved', 'ignored')) DEFAULT 'pending',
                    resolution_strategy TEXT,
                    representative_txn_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP,
                    notes TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS duplicate_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    similarity_score REAL NOT NULL,
                    source_name TEXT,
                    is_representative BOOLEAN DEFAULT 0,
                    FOREIGN KEY (group_id) REFERENCES duplicate_groups(group_id),
                    UNIQUE(group_id, transaction_id)
                )
            """)
            
            # Indexes for duplicate detection
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dup_groups_status ON duplicate_groups(resolution_status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dup_candidates_group ON duplicate_candidates(group_id)")
            
            conn.commit()
            logger.info("Database schema initialized")
    
    def _generate_transaction_hash(self, txn: Transaction) -> str:
        """
        Generate unique hash for transaction to detect duplicates.
        
        Hash includes:
        - Date (normalized)
        - Type
        - Ticker or ISIN
        - Shares (rounded)
        - Price (rounded)
        - Total (rounded)
        """
        # Normalize date to start of day
        date_str = txn.date.strftime("%Y-%m-%d")
        
        # Use ticker or ISIN
        asset_id = txn.ticker or txn.isin or "UNKNOWN"
        
        # Round financial values to avoid floating point issues
        shares_str = f"{float(txn.shares):.6f}" if txn.shares else "0"
        price_str = f"{float(txn.price):.4f}" if txn.price else "0"
        total_str = f"{float(txn.total):.2f}" if txn.total else "0"
        
        # Create hash string
        hash_input = f"{date_str}|{txn.type.value}|{asset_id}|{shares_str}|{price_str}|{total_str}"
        
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    def _transaction_to_row(self, txn: Transaction, source_name: str, txn_hash: str) -> Dict:
        """Convert Transaction to database row with encryption."""
        row = {
            'id': f"{source_name}_{txn_hash[:16]}_{datetime.now().timestamp()}",
            'date': txn.date.isoformat(),
            'type': txn.type.value,
            'ticker': txn.ticker,
            'isin': txn.isin,
            'name': txn.name,
            'asset_type': txn.asset_type.value if txn.asset_type else None,
            
            # Encrypt sensitive fields
            'shares_enc': self.encryption.encrypt_decimal(txn.shares),
            'price_enc': self.encryption.encrypt_decimal(txn.price),
            'total_enc': self.encryption.encrypt_decimal(txn.total),
            'fees_enc': self.encryption.encrypt_decimal(txn.fees),
            'cost_basis_local_enc': self.encryption.encrypt_decimal(getattr(txn, 'cost_basis_local', None)),
            'cost_basis_eur_enc': self.encryption.encrypt_decimal(getattr(txn, 'cost_basis_eur', None)),
            'fx_rate_enc': self.encryption.encrypt_decimal(getattr(txn, 'fx_rate', None)),
            
            'currency': txn.currency,
            'original_currency': getattr(txn, 'original_currency', txn.currency),
            'source_name': source_name,
            'source_import_date': datetime.now().isoformat(),
            'transaction_hash': txn_hash,
            'broker': getattr(txn, 'broker', None),
        }
        
        return row
    
    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        """Convert database row to Transaction with decryption."""
        return Transaction(
            date=datetime.fromisoformat(row['date']).date(),
            type=TransactionType(row['type']),
            ticker=row['ticker'],
            isin=row['isin'],
            name=row['name'],
            asset_type=AssetType(row['asset_type']) if row['asset_type'] else AssetType.UNKNOWN,
            
            # Decrypt sensitive fields
            shares=self.encryption.decrypt_decimal(row['shares_enc']) or Decimal(0),
            price=self.encryption.decrypt_decimal(row['price_enc']) or Decimal(0),
            total=self.encryption.decrypt_decimal(row['total_enc']) or Decimal(0),
            fees=self.encryption.decrypt_decimal(row['fees_enc']) or Decimal(0),
            
            currency=row['currency'] or 'EUR',
            original_currency=row['original_currency'] or row['currency'] or 'EUR',
            broker=row['broker'],
            
            # Additional fields
            cost_basis_local=self.encryption.decrypt_decimal(row['cost_basis_local_enc']),
            cost_basis_eur=self.encryption.decrypt_decimal(row['cost_basis_eur_enc']),
            fx_rate=self.encryption.decrypt_decimal(row['fx_rate_enc']) or Decimal(1),
        )
    
    def append_transactions(
        self,
        transactions: List[Transaction],
        source_name: str,
        dedup_strategy: str = "hash_first"
    ) -> ImportResult:
        """
        Add transactions to the store with deduplication.
        
        Args:
            transactions: List of transactions to add
            source_name: Identifier for this data source
            dedup_strategy: "hash_first" (skip exact duplicates) or "keep_all"
        
        Returns:
            ImportResult with counts and any errors
        """
        added = 0
        skipped = 0
        errors = []
        
        with self._get_conn() as conn:
            for txn in transactions:
                try:
                    txn_hash = self._generate_transaction_hash(txn)
                    
                    # Check if hash already exists
                    if dedup_strategy == "hash_first":
                        existing = conn.execute(
                            "SELECT id FROM transactions WHERE transaction_hash = ?",
                            (txn_hash,)
                        ).fetchone()
                        
                        if existing:
                            skipped += 1
                            continue
                    
                    # Convert to row and insert
                    row = self._transaction_to_row(txn, source_name, txn_hash)
                    
                    placeholders = ', '.join(['?' for _ in row])
                    columns = ', '.join(row.keys())
                    
                    conn.execute(
                        f"INSERT INTO transactions ({columns}) VALUES ({placeholders})",
                        list(row.values())
                    )
                    
                    added += 1
                    
                except Exception as e:
                    errors.append(f"Error adding transaction: {str(e)}")
                    logger.error(f"Failed to add transaction: {e}", exc_info=True)
            
            conn.commit()
        
        # Record import history
        self._record_import(source_name, added, skipped, len(errors))
        
        logger.info(f"Import complete: {added} added, {skipped} skipped, {len(errors)} errors")
        
        return ImportResult(
            added=added,
            skipped=skipped,
            flagged_for_review=0,
            total_count=len(transactions),
            errors=errors
        )
    
    def _record_import(self, source_name: str, added: int, skipped: int, error_count: int):
        """Record import to history table."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO import_history 
                (import_id, import_date, source_name, transactions_added, 
                 transactions_skipped, transactions_flagged, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{source_name}_{datetime.now().timestamp()}",
                datetime.now().isoformat(),
                source_name,
                added,
                skipped,
                0,
                "success" if error_count == 0 else "partial"
            ))
            conn.commit()
    
    def get_all_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        source_filter: Optional[List[str]] = None
    ) -> List[Transaction]:
        """
        Retrieve all transactions with optional filters.
        
        Args:
            start_date: Optional minimum date
            end_date: Optional maximum date
            source_filter: Optional list of source names to include
        
        Returns:
            List of Transaction objects (decrypted)
        """
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        
        if source_filter:
            placeholders = ','.join(['?' for _ in source_filter])
            query += f" AND source_name IN ({placeholders})"
            params.extend(source_filter)
        
        query += " ORDER BY date ASC"
        
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        
        transactions = []
        for row in rows:
            try:
                txn = self._row_to_transaction(row)
                transactions.append(txn)
            except Exception as e:
                logger.error(f"Failed to decrypt transaction {row['id']}: {e}")
        
        logger.info(f"Retrieved {len(transactions)} transactions")
        return transactions
    
    def get_sources(self) -> List[str]:
        """Get list of all unique source names."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT source_name FROM transactions ORDER BY source_name"
            ).fetchall()
        return [row['source_name'] for row in rows]
    
    def delete_by_source(self, source_name: str) -> int:
        """
        Delete all transactions from a specific source.
        
        Args:
            source_name: Name of source to delete
        
        Returns:
            Number of transactions deleted
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM transactions WHERE source_name = ?",
                (source_name,)
            )
            deleted = cursor.rowcount
            conn.commit()
        
        logger.info(f"Deleted {deleted} transactions from source: {source_name}")
        return deleted
    
    def get_import_history(self, limit: int = 50) -> List[Dict]:
        """
        Get recent import history.
        
        Args:
            limit: Maximum number of records to return
        
        Returns:
            List of import history records
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM import_history ORDER BY import_date DESC LIMIT ?",
                (limit,)
            ).fetchall()
        
        return [dict(row) for row in rows]
    
    def get_transaction_count_by_source(self) -> Dict[str, int]:
        """Get count of transactions per source."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT source_name, COUNT(*) as count 
                FROM transactions 
                GROUP BY source_name
                ORDER BY source_name
            """).fetchall()
        
        return {row['source_name']: row['count'] for row in rows}
    
    def find_near_duplicates(
        self,
        min_score: float = 60.0
    ) -> List['DuplicateGroup']:
        """
        Find near-duplicate transactions using ISIN-based matching.
        
        Args:
            min_score: Minimum similarity score (default 60)
        
        Returns:
            List of DuplicateGroup objects
        """
        from calculators.duplicate_detector import DuplicateDetector
        
        # Get all transactions
        transactions = self.get_all_transactions()
        
        # Run detection
        detector = DuplicateDetector()
        groups = detector.find_duplicate_groups(transactions, min_score)
        
        # Store groups in database
        with self._get_conn() as conn:
            for group in groups:
                # Insert group
                conn.execute("""
                    INSERT OR IGNORE INTO duplicate_groups 
                    (group_id, group_type, resolution_status)
                    VALUES (?, ?, 'pending')
                """, (group.group_id, group.group_type.value))
                
                # Insert candidates
                for candidate in group.candidates:
                    # Find transaction ID
                    txn_hash = self._generate_transaction_hash(candidate.transaction)
                    txn_row = conn.execute(
                        "SELECT id FROM transactions WHERE transaction_hash = ? LIMIT 1",
                        (txn_hash,)
                    ).fetchone()
                    
                    if txn_row:
                        conn.execute("""
                            INSERT OR IGNORE INTO duplicate_candidates
                            (group_id, transaction_id, similarity_score, source_name)
                            VALUES (?, ?, ?, ?)
                        """, (
                            group.group_id,
                            txn_row['id'],
                            candidate.similarity_score,
                            candidate.source_name
                        ))
            
            conn.commit()
        
        logger.info(f"Found {len(groups)} duplicate groups")
        return groups
    
    def get_pending_duplicate_count(self) -> int:
        """Get count of pending duplicate groups."""
        with self._get_conn() as conn:
            result = conn.execute("""
                SELECT COUNT(*) as count 
                FROM duplicate_groups 
                WHERE resolution_status = 'pending'
            """).fetchone()
            return result['count'] if result else 0
    
    def get_pending_duplicate_groups(self) -> List[Dict]:
        """
        Get all pending duplicate groups with their candidates.
        
        Returns:
            List of dicts with group info and candidate transactions
        """
        groups = []
        
        with self._get_conn() as conn:
            # Get all pending groups
            group_rows = conn.execute("""
                SELECT * FROM duplicate_groups 
                WHERE resolution_status = 'pending'
                ORDER BY created_at DESC
            """).fetchall()
            
            for group_row in group_rows:
                # Get candidates for this group
                candidate_rows = conn.execute("""
                    SELECT dc.*, t.*
                    FROM duplicate_candidates dc
                    JOIN transactions t ON dc.transaction_id = t.id
                    WHERE dc.group_id = ?
                    ORDER BY dc.similarity_score DESC
                """, (group_row['group_id'],)).fetchall()
                
                candidates = []
                for cand_row in candidate_rows:
                    try:
                        txn = self._row_to_transaction(cand_row)
                        candidates.append({
                            'transaction': txn,
                            'similarity_score': cand_row['similarity_score'],
                            'source_name': cand_row['source_name'],
                            'transaction_id': cand_row['transaction_id']
                        })
                    except Exception as e:
                        logger.error(f"Error loading candidate: {e}")
                
                groups.append({
                    'group_id': group_row['group_id'],
                    'group_type': group_row['group_type'],
                    'candidates': candidates,
                    'created_at': group_row['created_at']
                })
        
        return groups
    
    def resolve_duplicate_group(
        self,
        group_id: str,
        strategy: str,
        keep_transaction_id: Optional[str] = None
    ) -> bool:
        """
        Resolve a duplicate group.
        
        Args:
            group_id: ID of duplicate group
            strategy: 'keep_first', 'keep_specific', 'keep_all', 'ignore'
            keep_transaction_id: ID of transaction to keep (if strategy='keep_specific')
        
        Returns:
            True if successful
        """
        try:
            with self._get_conn() as conn:
                if strategy == 'keep_all':
                    # Mark as not duplicates
                    conn.execute("""
                        UPDATE duplicate_groups 
                        SET resolution_status = 'ignored',
                            resolution_strategy = 'keep_all',
                            resolved_at = ?
                        WHERE group_id = ?
                    """, (datetime.now().isoformat(), group_id))
                    
                elif strategy in ['keep_first', 'keep_specific']:
                    # Get candidates
                    candidates = conn.execute("""
                        SELECT transaction_id 
                        FROM duplicate_candidates 
                        WHERE group_id = ?
                        ORDER BY similarity_score DESC
                    """, (group_id,)).fetchall()
                    
                    if not candidates:
                        return False
                    
                    # Determine which to keep
                    if strategy == 'keep_first':
                        keep_id = candidates[0]['transaction_id']
                    else:
                        keep_id = keep_transaction_id
                    
                    # Delete other candidates
                    to_delete = [c['transaction_id'] for c in candidates if c['transaction_id'] != keep_id]
                    
                    for txn_id in to_delete:
                        conn.execute(
                            "DELETE FROM transactions WHERE id = ?",
                            (txn_id,)
                        )
                    
                    # Mark group as resolved
                    conn.execute("""
                        UPDATE duplicate_groups 
                        SET resolution_status = 'resolved',
                            resolution_strategy = ?,
                            representative_txn_id = ?,
                            resolved_at = ?
                        WHERE group_id = ?
                    """, (strategy, keep_id, datetime.now().isoformat(), group_id))
                
                conn.commit()
                logger.info(f"Resolved duplicate group {group_id} with strategy: {strategy}")
                return True
                
        except Exception as e:
            logger.error(f"Error resolving duplicate group: {e}")
            return False
