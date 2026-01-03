"""
Database Reset Utility

 SAFELY Deletes the current SQLite database to force a full re-ingestion of all CSV files.
 This is necessary when the database schema or data integrity is compromised (e.g. ISIN/Ticker mixups).
"""

import os
import shutil
from pathlib import Path
import streamlit as st
import time

# Metrics
from lib.utils.logging_config import setup_logger
logger = setup_logger(__name__)

DB_PATH = Path("data/transactions.db")
BACKUP_DIR = Path("data/backups")

def reset_database():
    st.title("🧨 Database Reset Utility")
    st.markdown("### ⚠️ Danger Zone")
    st.markdown("This will **DELETE** your current transaction database. All CSV files in `data/` will be re-processed on next app load.")
    
    if st.button("💣 DELETE DATABASE AND RESET", type="primary"):
        try:
            if DB_PATH.exists():
                # 1. Backup
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                backup_path = BACKUP_DIR / f"transactions_backup_{timestamp}.db"
                shutil.copy2(DB_PATH, backup_path)
                st.success(f"✅ Backup created at `{backup_path}`")
                
                # 2. Delete
                os.remove(DB_PATH)
                st.success(f"🗑️ Database `{DB_PATH}` deleted successfully.")
                
                # 3. Clear Streamlit Cache
                st.cache_data.clear()
                st.success("🧹 Streamlit cache cleared.")
                
                st.info("🔄 Please restart the application (or reload the page) to trigger re-ingestion.")
            else:
                st.warning("Database file not found. Nothing to delete.")
                
        except Exception as e:
            st.error(f"❌ Error during reset: {e}")
            logger.error(f"Database reset failed: {e}")

if __name__ == "__main__":
    reset_database()
