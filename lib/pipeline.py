
# -----------------------------------------------------------------------------
# (c) 2026 Andreas Wagner. All Rights Reserved.
#
# This code is part of the Portfolio Viewer project.
# Unauthorized usage or distribution is not permitted.
# -----------------------------------------------------------------------------

import streamlit as st
from decimal import Decimal
from lib.parsers.csv_parser import CSVParser
from lib.parsers.ibkr_flex_parser import IbkrFlexParser
from lib.isin_resolver import ISINResolver
from lib.corporate_actions import CorporateActionService
from lib.fx_rates import FXRateService
from lib.validators import DataValidator
from lib.utils.logging_config import setup_logger

logger = setup_logger(__name__)

@st.cache_data(show_spinner="Loading chart data...", ttl=3600)
def process_data_pipeline(file_content: str):
    """
    Process CSV content into enriched transactions with caching.
    """
    try:
        # Detect parser type
        is_ibkr_flex = "ClientAccountID" in file_content and "TransactionType" in file_content
        
        if is_ibkr_flex:
            logger.info("Detected Interactive Brokers Flex Query format")
            parser = IbkrFlexParser()
            transactions = parser.parse(file_content)
        else:
            parser = CSVParser()
            transactions = parser.parse_csv(file_content)
        
        if not transactions:
            return [], [], 0
        
        # Collect all identifiers that need resolution (ISINs)
        isins_to_resolve = []
        for t in transactions:
            # If transaction has ISIN but no ticker, we need to resolve it
            if not t.ticker and t.isin:
                isins_to_resolve.append(t.isin)
            # If ticker looks like an ISIN, resolve it too
            elif t.ticker and len(t.ticker) == 12 and t.ticker[:2].isalpha():
                isins_to_resolve.append(t.ticker)
        
        # Resolve ISINs to tickers
        resolved_map = {}
        if isins_to_resolve:
            resolved_map = ISINResolver.resolve_batch(list(set(isins_to_resolve)))
            
        # Update transactions with resolved tickers
        resolved_count = 0
        for t in transactions:
            # Case 1: Has ISIN but no ticker - resolve ISIN and set ticker
            if not t.ticker and t.isin:
                if t.isin in resolved_map:
                    resolved_ticker = resolved_map[t.isin]
                    # Only use resolved ticker if it's different from ISIN (i.e., actually resolved)
                    if resolved_ticker != t.isin:
                        t.ticker = resolved_ticker
                        resolved_count += 1
                        logger.debug(f"Resolved ISIN {t.isin} → {t.ticker}")
                    else:
                        # Resolution failed - skip this transaction or log warning
                        logger.warning(f"Could not resolve ISIN {t.isin} to ticker - transaction may be skipped")
            
            # Case 2: Ticker looks like an ISIN - try to resolve it
            elif t.ticker and len(t.ticker) == 12 and t.ticker[:2].isalpha():
                if t.ticker in resolved_map:
                    resolved_ticker = resolved_map[t.ticker]
                    if resolved_ticker != t.ticker:
                        old_ticker = t.ticker
                        t.ticker = resolved_ticker
                        resolved_count += 1
                        logger.debug(f"Resolved ISIN-like ticker {old_ticker} → {t.ticker}")
                        
        if resolved_count > 0:
            logger.info(f"Resolved ISINs to Tickers for {resolved_count} transactions")
        
        # Corporate Actions (Splits, Spin-offs, Mergers)
        transactions, corporate_log = CorporateActionService.detect_and_apply_all_actions(
            transactions,
            fetch_splits=True
        )
        
        # FX Rates & Normalization (User Constraint: Store everything as EUR)
        fx_conversions = 0
        for trans in transactions:
            # Always ensure we have an FX rate relative to EUR
            if trans.original_currency != 'EUR':
                # Fetch historical FX rate for this transaction date
                historical_rate, rate_source = FXRateService.get_rate(
                    trans.original_currency,
                    'EUR',
                    trans.date.date()
                )
                
                # Update FX rate
                trans.fx_rate = historical_rate
                
                # NORMALIZE TO EUR IMMEDIATELY
                # We overwrite the main fields with EUR values so the rest of the app 
                # (Store, Tax, Portfolio) only sees EUR.
                if trans.fx_rate and trans.fx_rate != 1:
                    trans.price = trans.price * trans.fx_rate
                    trans.total = trans.total * trans.fx_rate
                    trans.fees = trans.fees * trans.fx_rate
                    trans.withholding_tax = trans.withholding_tax * trans.fx_rate
                    fx_conversions += 1
                    
                    logger.debug(f"Normalized {trans.ticker} to EUR @ {trans.fx_rate}: {trans.price:.2f} EUR")
            else:
                trans.fx_rate = Decimal(1)

        
        # Validation performed outside to avoid serialization issues
        
        return transactions, corporate_log, fx_conversions
        
    except Exception as e:
        logger.error(f"Pipeline processing error: {e}", exc_info=True)
        raise e


def parse_csv_only(file_content: str):
    """
    Parse CSV without tx enrichment.
    """
    try:
        parser = CSVParser()
        transactions = parser.parse_csv(file_content)
        
        if not transactions:
            return None, None
        
        # Light validation only
        validator = DataValidator()
        validation_issues = validator.validate_all(transactions)
        val_summary = validator.get_summary()
        
        return transactions, (validation_issues, val_summary)
        
    except Exception as e:
        logger.error(f"CSV parsing error: {e}", exc_info=True)
        raise e
