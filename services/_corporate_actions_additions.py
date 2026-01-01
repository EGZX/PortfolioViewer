# Add these methods to the end of CorporateActionService class

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
