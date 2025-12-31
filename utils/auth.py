"""Password authentication module using Streamlit secrets."""

import streamlit as st
import hashlib
import hmac
import os
import time
import random
import base64
from typing import Optional

# Configuration
ITERATIONS = 600_000  # OWASP recommended iteration count for PBKDF2-HMAC-SHA256 (2023)
SALT_SIZE = 32        # 32 bytes = 256 bits

def hash_password(password: str) -> str:
    """
    Hash a password using PBKDF2-HMAC-SHA256 with a random salt.
    
    Format: pbkdf2_sha256$iterations$salt_b64$hash_b64
    """
    salt = os.urandom(SALT_SIZE)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        ITERATIONS
    )
    
    salt_b64 = base64.b64encode(salt).decode('ascii')
    key_b64 = base64.b64encode(key).decode('ascii')
    
    return f"pbkdf2_sha256${ITERATIONS}${salt_b64}${key_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify a password against its stored hash.
    Strictly forces PBKDF2 format.
    """
    try:
        # Parse PBKDF2 format
        if '$' not in stored_hash:
            return False
            
        parts = stored_hash.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
            
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected_key = base64.b64decode(parts[3])
        
        # Calculate hash with extracted salt/iterations
        derived_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            iterations
        )
        
        # Constant time comparison
        return hmac.compare_digest(derived_key, expected_key)
        
    except Exception:
        return False


def check_authentication() -> bool:
    """
    Check if user is authenticated.
    
    Implements:
    - Session timeout (30 min)
    - Anti-brute force delay
    - Fail-secure configuration check
    """
    # Session Timeout Logic
    if "last_activity" in st.session_state:
        if time.time() - st.session_state["last_activity"] > 1800:  # 30 minutes
            st.session_state["authenticated"] = False
            st.session_state.pop("last_activity", None)
            st.warning("Session timed out due to inactivity. Please log in again.")
            st.rerun()
            return False
            
    # Update activity timestamp
    st.session_state["last_activity"] = time.time()

    # Check if already authenticated in session
    if st.session_state.get("authenticated", False):
        return True
    
    # Get expected hash from secrets
    try:
        if "passwords" not in st.secrets:
             st.error("Configuration Error: 'passwords' section missing in secrets.toml.")
             return False

        expected_hash = st.secrets["passwords"].get("app_password_hash")
        
        if not expected_hash:
            st.error("Configuration Error: 'app_password_hash' not configured.")
            return False
            
    except Exception as e:
        st.error(f"Configuration Error: Could not load secrets ({str(e)}).")
        return False
    
    # Login Interface
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container(border=True):
            st.markdown('<div style="text-align: center; margin-bottom: 20px;">ACCESS CONTROL</div>', unsafe_allow_html=True)
            
            password_input = st.text_input(
                "PASSPHRASE",
                type="password",
                key="password_input",
                label_visibility="visible"
            )
            
            submit_col1, submit_col2, submit_col3 = st.columns([1, 2, 1])
            with submit_col2:
                login_button = st.button("AUTHENTICATE", type="primary", use_container_width=True)
    
    if login_button:
        # Verify Password
        if verify_password(password_input, expected_hash):
            st.session_state["authenticated"] = True
            st.success("ACCESS GRANTED")
            st.rerun()
        else:
            # Anti-brute force delay
            time.sleep(1.0 + random.random())
            
            st.error("Invalid Passphrase")
            return False
    
    return False


def logout():
    """Log out the current user."""
    st.session_state["authenticated"] = False
    st.rerun()


def show_logout_button():
    """Display logout button in sidebar."""
    with st.sidebar:
        st.divider()
        if st.button("Logout", help="Log out of the application"):
            logout()


def generate_password_hash(password: str) -> str:
    """
    Generate a secure hash for a password (for initial setup).
    Uses PBKDF2-HMAC-SHA256.
    """
    return hash_password(password)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        password = sys.argv[1]
        print(f"Generating Secure Hash for '{password}'...")
        h = generate_password_hash(password)
        print(f"\nHash: {h}")
        print("\nUpdate .streamlit/secrets.toml with:")
        print(f'[passwords]\napp_password_hash = "{h}"')
    else:
        print("Usage: python auth.py <password>")
