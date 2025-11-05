from flask import Flask, request, jsonify
from flask_cors import CORS # NEW: Import CORS
import requests
import smtplib
from email.mime.text import MIMEText
from threading import Thread
import time
import os
import json

# --- Configuration: Reads from Environment Variables (CORRECTED) ---
try:
    # ⚠️ IMPORTANT: These must be the names of the variables set on Render
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com") 
    SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY", "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")  # Private App Access Token
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj")  # App Password for email
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10") 
    # Storefront URL for notification links (e.g., "https://raj-dynamic-dreamz.myshopify.com")
    STOREFRONT_BASE_URL = os.environ.get("STOREFRONT_BASE_URL", f"https://{SHOPIFY_STORE_URL}")
except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. Please check configuration. {e}")

app = Flask(__name__)

# --- CRITICAL FIX: Configure CORS to allow cross-origin requests from your Shopify store ---
# This line tells the browser that requests from your Shopify domain are safe.
if STOREFRONT_BASE_URL:
    # Allow only the specific store domain (safer)
    CORS(app, resources={r"/*": {"origins": STOREFRONT_BASE_URL}})
else:
    # Default to allowing all origins if base URL is not set (less secure, but avoids errors)
    CORS(app) 

# Simple in-memory storage for demonstration (USE A DATABASE FOR PRODUCTION)
# Format: {email: product_variant_id, ...}
waitlist = {}

# --- Shopify API Helper ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY:
        print("Configuration missing: Shopify URL or API Key is empty.")
        return False
        
    # Shopify variant IDs can be very long (e.g., 81234567890). Assuming it's the raw ID here.
    numeric_id = str(variant_id).split('/')[-1]

    # Construct clean URL
    url = (
        f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{numeric_id}.json"
    )

    # Use the correct authentication header
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_API_KEY
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        inventory_quantity = data['variant']['inventory_quantity']
        print(f"Stock check for variant {variant_id}: {inventory_quantity} available.")
        return inventory_quantity > 0
    except requests.exceptions.RequestException as e:
        print(f"Shopify API Error checking variant {variant_id}. Response status: {response.status_code if 'response' in locals() else 'N/A'}. Error: {e}")
        return False

# --- Email Helper ---
def send_email(to_email, subject, body):
    """Sends an email using the configured SMTP settings."""
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        print("Email configuration missing.")
        return False
        
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
            print(f"Email sent successfully to {to_email}")
            return True
    except Exception as e:
        print(f"Email sending failed to {to_email}: {e}")
        return False

# --- Endpoints ---

@app.route('/', methods=['GET'])
def home():
    """Simple check for Render health check."""
    # This also resolves the 404 errors seen in your logs for GET /
    return "Shopify Waitlist Service is running.", 200

@app.route('/notify-signup', methods=['POST'])
def notify_signup():
    """Handles the user sign-up request from the Shopify Liquid template."""
    try:
        # Check Content-Type for Flask's request.get_json()
        if request.content_type != 'application/json':
             return jsonify({"error": "Content-Type must be application/json."}), 415

        data = request.get_json()
        email = data.get('email')
        variant_id = data.get('variant_id')

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        # Add user to the waitlist (overwrite existing if they re-subscribe)
        waitlist[email] = variant_id
        
        # 1. Send initial confirmation email
        initial_subject = "✅ You're on the Waitlist!"
        initial_body = (
            f"Thanks! We've added your email, {email}, to the notification list. "
            "We will send you a second email the moment the product is back in stock."
        )
        send_email(email, initial_subject, initial_body)

        # IMPORTANT: Return success message immediately to the Shopify storefront
        return jsonify({"message": "Successfully added to the waitlist. Confirmation email sent."}), 200
        
    except Exception as e:
        print(f"Error processing sign-up request: {e}")
        return jsonify({"error": "Internal server error during processing."}), 500


# --- Background Stock Checker ---

def stock_checker_task():
    """Background task to periodically check stock and send notifications."""
    global waitlist
    print("Stock checker thread started.")
    time.sleep(60) # Wait 1 minute before first check
    
    while True:
        print(f"Starting stock check cycle. Waitlist size: {len(waitlist)}")
        time.sleep(900) # Check stock every 15 minutes
        
        # Use a copy of keys for safe iteration while modifying the waitlist
        emails_to_check = list(waitlist.keys())
        notified_emails = [] 
        
        for email in emails_to_check:
            variant_id = waitlist.get(email)
            if variant_id is None:
                continue

            if check_shopify_stock(variant_id):
                # Product is IN STOCK!
                
                # 2. Send in-stock notification email
                notification_subject = "🎉 IN STOCK NOW! Buy Before It Sells Out!"
                notification_body = (
                    f"Great news, {email}! The product you were waiting for "
                    "is officially back in stock! \n\n"
                    "Don't wait, buy it here: "
                    # Construct a generic link using the variant ID. You should ideally use a product handle here.
                    f"{STOREFRONT_BASE_URL}/cart/{variant_id}:1" 
                    "\n\nNote: This link adds one item directly to your cart."
                )
                
                if send_email(email, notification_subject, notification_body):
                    notified_emails.append(email)

        # Safely remove notified customers
        for email in notified_emails:
            if email in waitlist:
                del waitlist[email]
        
        print(f"Stock check cycle complete. {len(notified_emails)} notifications sent.")


# --- Run Application ---
if __name__ == '__main__':
    # Start the background thread for stock checking
    stock_thread = Thread(target=stock_checker_task)
    stock_thread.daemon = True 
    stock_thread.start()
    
    # Render uses the PORT environment variable, defaults to 8080
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080))
