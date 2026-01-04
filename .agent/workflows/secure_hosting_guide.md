---
description: How to securely host the Portfolio Viewer locally and expose it to the public without uploading data.
---

# Secure Local Hosting Guide

This guide explains how to share your Portfolio Viewer with others securely while keeping all your financial data (database and cache) on your local machine.

## Prerequisites

1.  **Application Running**: You should be able to run the app locally (`streamlit run app/portfolio_viewer.py`).
2.  **Authentication Enabled**:
    The application has built-in authentication (`lib/utils/auth.py`). 
    **Crucial**: Ensure you have set a strong password in `.streamlit/secrets.toml`.
    
    To generate a new password hash:
    ```powershell
    python lib/utils/auth.py "YourStrongPasswordHere"
    ```
    Update your `.streamlit/secrets.toml` with the generated hash.

## Option 1: Cloudflare Tunnel (Recommended)

Cloudflare Tunnel creates a secure, encrypted link between your PC and the internet without opening ports on your router.

### Steps:

1.  **Download Cloudflared**:
    Download the `cloudflared` executable for Windows from [Cloudflare Downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-doh/get-started/cloudflared-loaders/).

2.  **Start your App**:
    Open a terminal and run your app as usual:
    ```powershell
    streamlit run app/portfolio_viewer.py
    ```
    (Ensure it is running at `http://localhost:8501`)

3.  **Start the Tunnel**:
    Open a *new* PowerShell window and run:
    ```powershell
    # Replace path/to/cloudflared with actual path if not in PATH
    .\cloudflared.exe tunnel --url http://localhost:8501
    ```

4.  **Share the URL**:
    Cloudflare will output a URL ending in `.trycloudflare.com` (e.g., `https://funny-name.trycloudflare.com`).
    
    *   **Share this URL** with your guests.
    *   When they access it, they will see your Login Screen.
    *   HTTPS is handled automatically.

**Note**: This "Quick Tunnel" changes URLs every time you restart `cloudflared`.

### How to make the URL permanent?

If you want a fixed URL (e.g., `portfolio.mydomain.com`) that doesn't change:

1.  **Cloudflare Named Tunnel (Requires a Domain)**:
    *   You need a free Cloudflare account and a registered domain name connected to Cloudflare.
    *   Run `cloudflared tunnel login`.
    *   Create a tunnel: `cloudflared tunnel create portfolio`.
    *   Route traffic: `cloudflared tunnel route dns portfolio portfolio.mydomain.com`.
    *   Run it: `cloudflared tunnel run portfolio`.

2.  **Tailscale Funnel (Free, No Domain needed)**:
    *   If you use Tailscale, your node gets a stable name (like `http://my-pc.tailnet.ts.net`).
    *   Enabling Funnel exposes this stable URL to the public internet securely.
    *   This is often the easiest way to get a **permanent** free link.

## Option 2: Tailscale Funnel (For Tailscale Users)

If you use Tailscale, "Funnel" is an easy way to expose the service.

1.  **Serve the App**:
    ```powershell
    tailscale funnel 8501
    ```
2.  **Access**:
    Share your machine's public Tailscale URL (e.g., `https://machine-name.tailnet.ts.net`).
    This URL stays the same as long as you don't change your Tailscale node name.

## Important: "Permanent" vs "Online"

Because you are hosting this **on your own computer**:
1.  **The Link**: Can be made permanent (using the methods above).
2.  **The Service**: Is **ONLY** online when your computer is **ON** and the app is **RUNNING**.
    *   If you put your PC to sleep -> The site goes down.
    *   If you close the terminal -> The site goes down.


## Security Considerations

*   **Data Safety**: Since the app runs on your PC, the database files (`data/portfolio.db`) never leave your computer. The remote user only receives the HTML/UI.
*   **Authentication**: The app's built-in password screen is the primary barrier. Ensure your password is strong.
*   **Availability**: The link only works while your computer is on and the app is running.
