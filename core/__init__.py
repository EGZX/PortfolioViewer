"""
Core Kernel Module

The "Kernel" of the Portfolio Platform - provides foundational data access and utilities.

Components:
- db: DuckDB + SQLite connection manager (The Glue)
- market: Market data fetcher with Parquet storage
- hashing: SHA256 audit logic for immutable records

Copyright (c) 2026 Andreas Wagner. All rights reserved.
"""

__all__ = ['db', 'market', 'hashing']
