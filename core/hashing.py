"""
Hashing Module - SHA256 Audit Logic

Provides canonical JSON serialization and SHA256 hashing for creating
immutable audit trails. Used by the Tax Engine for calculation verification.

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict


def canonical_json_dumps(obj: Any) -> str:
    """
    Serialize object to canonical JSON string.
    
    Ensures deterministic serialization for hashing:
    - Keys sorted alphabetically
    - No whitespace
    - Consistent number formatting
    - Date/Decimal conversion
    
    Args:
        obj: Object to serialize (dict, list, or primitive)
    
    Returns:
        Canonical JSON string
    
    Example:
        >>> canonical_json_dumps({"amount": Decimal("123.45"), "date": date(2024, 1, 15)})
        '{"amount":123.45,"date":"2024-01-15"}'
    """
    def default_handler(o):
        if isinstance(o, Decimal):
            return float(o)
        elif isinstance(o, (date, datetime)):
            return o.isoformat()
        elif hasattr(o, '__dict__'):
            return o.__dict__
        else:
            raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")
    
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(',', ':'),
        default=default_handler,
        ensure_ascii=True
    )


def calculate_sha256(data: Any) -> str:
    """
    Calculate SHA256 hash of data.
    
    Args:
        data: Data to hash (will be serialized to JSON)
    
    Returns:
        SHA256 hex digest prefixed with 'sha256:'
    
    Example:
        >>> calculate_sha256({"event_id": "TAX_2024_001"})
        'sha256:...'
    """
    json_str = canonical_json_dumps(data)
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    return f"sha256:{hash_obj.hexdigest()}"


def verify_hash(data: Any, expected_hash: str) -> bool:
    """
    Verify that data matches expected hash.
    
    Args:
        data: Data to verify
        expected_hash: Expected hash (with 'sha256:' prefix)
    
    Returns:
        True if hash matches, False otherwise
    """
    actual_hash = calculate_sha256(data)
    return actual_hash == expected_hash


def create_audit_entry(event_id: str, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an audit trail entry with hash seal.
    
    Args:
        event_id: Unique identifier for this event
        inputs: Input data for the calculation
        outputs: Output/results of the calculation
    
    Returns:
        Audit entry dict with:
        - event_id
        - timestamp
        - calculation_hash (seals inputs + outputs)
        - inputs
        - outputs
    
    Example:
        >>> entry = create_audit_entry(
        ...     "TAX_2024_001",
        ...     {"shares": 100, "price": 50.0},
        ...     {"tax_due": 123.80}
        ... )
    """
    timestamp = datetime.utcnow()
    
    # Create composite object for hashing
    hashable_data = {
        "event_id": event_id,
        "timestamp": timestamp,
        "inputs": inputs,
        "outputs": outputs
    }
    
    calculation_hash = calculate_sha256(hashable_data)
    
    return {
        "event_id": event_id,
        "timestamp": timestamp.isoformat(),
        "calculation_hash": calculation_hash,
        "inputs": inputs,
        "outputs": outputs
    }
