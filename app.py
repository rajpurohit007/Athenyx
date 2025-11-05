from flask import Flask, request, jsonify
import requests
import smtplib
from email.mime.text import MIMEText
from threading import Thread
import time
import os
import json

# --- Configuration: Reads from Render Environment Variables ---
try:
    SHOPIFY_STORE_URL = os.environ.get("raj-dynamic-dreamz.myshopify.com") # e.g., "my-store-123.myshopify.com"
    SHOPIFY_API_KEY = os.environ.get("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")     # Private App Access Token
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("vvhj rkau nncu ugdj")       # App Password for email
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10") 
except Exception as e:
    print(f"ERROR: Failed to load environment variables. Please check Render configuration. {e}")

app = Flask(__name__)

# Simple in-memory storage for demonstration (USE A DATABASE FOR PRODUCTION)
# Format: {email: product_variant_id, ...}
waitlist = {}

# --- Shopify API Helper ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY:
        return False
        
    numeric_id = str(variant_id).split('/')[-1]

    # Construct URL with basic authentication (API Key in URL)
    url = (
        f"https://{SHOPIFY_API_KEY}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{numeric_id}.json"
    )

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        inventory_quantity = data['variant']['inventory_quantity']
        return inventory_quantity > 0
    except requests.exceptions.RequestException as e:
        print(f"Shopify API Error checking variant {variant_id}: {e}")
        return False

# --- Email Helper ---
def send_email(to_email, subject, body):
    """Sends an email using the configured SMTP settings."""
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
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

@app.route('/notify-signup', methods=['POST'])
def notify_signup():
    """Handles the user sign-up request from the Shopify Liquid template."""
    try:
        data = request.get_json()
        email = data.get('email')
        variant_id = data.get('variant_id')

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        # Add user to the waitlist
        waitlist[email] = variant_id
        
        # 1. Send initial confirmation email (FIRST EMAIL)
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
    time.sleep(60) # Wait 1 minute before first check
    
    while True:
        time.sleep(900) # Check stock every 15 minutes
        
        notified_emails = [] 
        
        for email, variant_id in list(waitlist.items()):
            if check_shopify_stock(variant_id):
                # Product is IN STOCK!
                
                # 2. Send in-stock notification email (SECOND EMAIL)
                notification_subject = "🎉 IN STOCK NOW! Buy Before It Sells Out!"
                notification_body = (
                    f"Great news, {email}! The product you were waiting for "
                    "is officially back in stock! \n\n"
                    "Don't wait, buy it here: "
                    # IMPORTANT: Update this URL with your actual store/product link template!
                    f"https://{SHOPIFY_STORE_URL}/products/product-handle?variant={variant_id}"
                )
                
                if send_email(email, notification_subject, notification_body):
                    notified_emails.append(email)

        # Safely remove notified customers
        for email in notified_emails:
            if email in waitlist:
                del waitlist[email]


# --- Run Application ---
if __name__ == '__main__':
    stock_thread = Thread(target=stock_checker_task)
    stock_thread.daemon = True 
    stock_thread.start()
    
    # Render uses the PORT environment variable, defaults to 8080
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080))
