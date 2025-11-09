import os
import requests
import json

# --- 1. CONFIGURE THESE VALUES ---

# Your Render app's public URL. (e.g., "https://my-waitlist-app.onrender.com")
# IMPORTANT: Must be 'https://'
APP_BASE_URL = "https://YOUR_APP_NAME.onrender.com"

# The topic we want to subscribe to.
WEBHOOK_TOPIC = "inventory_levels/update"

# --- 2. GET THESE FROM YOUR ENV VARS (or paste them) ---
SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com")
SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY", "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")
SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10")

# --- 3. DO NOT EDIT BELOW THIS LINE ---

def register_webhook():
    """
    Sends a POST request to Shopify to register the webhook.
    """
    
    # This is the full URL Shopify will send POST requests to
    webhook_address = f"{APP_BASE_URL.rstrip('/')}/shopify-webhook-receiver"
    
    api_url = (
        f"https{SHOPIFY_STORE_URL.rstrip('/')}/admin/api/"
        f"{SHOPIFY_API_VERSION}/webhooks.json"
    )
    
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_API_KEY
    }
    
    payload = {
        "webhook": {
            "topic": WEBHOOK_TOPIC,
            "address": webhook_address,
            "format": "json"
        }
    }

    print(f"Attempting to register webhook for topic '{WEBHOOK_TOPIC}'...")
    print(f"Callback URL: {webhook_address}")
    
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload), timeout=10)
        
        if response.status_code == 201:
            print("\n✅ SUCCESS: Webhook registered successfully!")
            print("Shopify will now send real-time inventory updates to your app.")
            print("\n--- IMPORTANT ---")
            print("Go to your Shopify Admin (Settings > Notifications > Webhooks) to find the 'signing key'.")
            print("You MUST set this key as the 'SHOPIFY_WEBHOOK_SECRET' environment variable in Render.")
            
        elif response.status_code == 422:
            print("\n⚠️ WARNING: Webhook registration failed (422).")
            print("This usually means this webhook is ALREADY registered for this address.")
            print("Response:", response.json())
        else:
            response.raise_for_status()
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ ERROR: Webhook registration failed.")
        print(f"Details: {e}")
        if e.response:
            print("Response body:", e.response.text)

if __name__ == "__main__":
    if "YOUR_APP_NAME" in APP_BASE_URL:
        print("ERROR: Please edit the 'APP_BASE_URL' variable in this script first.")
    else:
        register_webhook()
