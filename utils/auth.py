"""Password authentication module using Streamlit secrets."""

import streamlit as st
import hashlib
from typing import Optional


def hash_password(password: str) -> str:
    """
    Hash a password using SHA-256.
    
    Args:
        password: Plain text password
    
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        password: Plain text password to verify
        hashed: Expected hash
    
    Returns:
        True if password matches, False otherwise
    """
    return hash_password(password) == hashed


def check_authentication() -> bool:
    """
    Check if user is authenticated.
    
    Uses Streamlit secrets for storing hashed password.
    Secrets should be configured in .streamlit/secrets.toml:
    
    [passwords]
    app_password_hash = "hashed_password_here"
    
    Returns:
        True if authenticated, False otherwise
    """
    # Check if already authenticated in session
    if st.session_state.get("authenticated", False):
        return True
    
    # Get expected hash from secrets
    try:
        expected_hash = st.secrets.get("passwords", {}).get("app_password_hash")
        
        if not expected_hash:
            # No password configured - allow access
            st.warning("⚠️ No password configured. Set 'passwords.app_password_hash' in .streamlit/secrets.toml for security.")
            st.session_state["authenticated"] = True
            return True
            
    except Exception as e:
        # Secrets file doesn't exist or other error - allow access with warning
        st.warning(f"⚠️ Could not load secrets: {e}. Access granted without authentication.")
        st.session_state["authenticated"] = True
        return True
    
    # Centered Login Card
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        with st.container(border=True):
            st.markdown('<div style="text-align: center; margin-bottom: 20px;">🔒 SECURE ACCESS</div>', unsafe_allow_html=True)
            
            password_input = st.text_input(
                "PASSPHRASE",
                type="password",
                key="password_input",
                help="Enter authorization key",
                label_visibility="visible"
            )
            
            submit_col1, submit_col2, submit_col3 = st.columns([1, 2, 1])
            with submit_col2:
                login_button = st.button("AUTHENTICATE", type="primary", use_container_width=True)
    
    if login_button:
        if verify_password(password_input, expected_hash):
            st.session_state["authenticated"] = True
            st.success("ACCESS GRANTED")
            st.rerun()
        else:
            st.error("ACCESS DENIED: Invalid Passphrase")
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
        if st.button("🚪 Logout", help="Log out of the application"):
            logout()


# Helper function to generate password hash for setup
def generate_password_hash(password: str) -> str:
    """
    Generate a hash for a password (for initial setup).
    
    Usage:
        python -c "from utils.auth import generate_password_hash; print(generate_password_hash('your_password'))"
    
    Args:
        password: Plain text password
    
    Returns:
        Hash to put in secrets.toml
    """
    return hash_password(password)


if __name__ == "__main__":
    # Quick hash generator
    import sys
    if len(sys.argv) > 1:
        password = sys.argv[1]
        print(f"Password hash for '{password}':")
        print(generate_password_hash(password))
        print("\nAdd this to .streamlit/secrets.toml:")
        print(f'[passwords]\napp_password_hash = "{generate_password_hash(password)}"')
    else:
        print("Usage: python auth.py <password>")
        print("Example: python auth.py mySecurePassword123")
