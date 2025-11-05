from flask import Flask, request, jsonify
import requests
import smtplib
from email.mime.text import MIMEText
from threading import Thread
import time
import os
import json

# --- Configuration: Reads from Render Environment Variables ---
# NOTE: You MUST set these variables in your Render service dashboard.
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

# Simple in-memory storage for demonstration (RECOMMEND USING A DATABASE FOR PRODUCTION)
# Format: {email: product_variant_id, ...}
waitlist = {}

# --- Shopify API Helper ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
    # Ensure all required Shopify credentials are set
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY:
        print("Shopify credentials missing. Cannot check stock.")
        return False
        
    # The variant ID might be a GID (e.g., "gid://shopify/ProductVariant/123456789")
    # We strip it down to the numeric ID for the REST API
    numeric_id = str(variant_id).split('/')[-1]

    url = (
        f"https://{SHOPIFY_API_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{numeric_id}.json"
    ).replace('SHOPIFY_API_STORE_URL', f"{SHOPIFY_API_KEY}@{SHOPIFY_STORE_URL}")

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        inventory_quantity = data['variant']['inventory_quantity']
        # Product is considered in stock if quantity is greater than 0
        return inventory_quantity > 0
    except requests.exceptions.RequestException as e:
        print(f"Shopify API Error checking variant {variant_id}: {e}")
        return False

# --- Email Helper ---
def send_email(to_email, subject, body):
    """Sends an email using the configured SMTP settings."""
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        print("Email credentials missing. Cannot send email.")
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
            print(f"Confirmation email sent successfully to {to_email}")
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
        variant_id = data.get('variant_id') # Received from the Liquid file

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        # Add or update the user in the waitlist
        waitlist[email] = variant_id
        
        # 1. Send initial confirmation email
        initial_subject = "✅ Product Waitlist Confirmation: You're In!"
        initial_body = (
            f"Thank you for your interest! We've added your email, {email}, "
            "to the notification list for the product. "
            "We will send you a second email the moment it is back in stock."
        )
        send_email(email, initial_subject, initial_body)

        return jsonify({"message": "Successfully added to the waitlist. Check your email for confirmation."}), 200
    
    except Exception as e:
        print(f"Error processing sign-up request: {e}")
        return jsonify({"error": "Internal server error during processing."}), 500


# --- Background Stock Checker ---

def stock_checker_task():
    """
    Background task to periodically check stock for all items in the waitlist 
    and send notifications when stock is found.
    """
    global waitlist
    
    # Wait 60 seconds after startup before starting checks
    time.sleep(60) 
    
    while True:
        # Check stock every 15 minutes (900 seconds)
        time.sleep(900) 
        
        notified_emails = [] 
        
        # Iterate over a copy of the waitlist to avoid runtime size changes
        for email, variant_id in list(waitlist.items()):
            print(f"Checking stock for variant {variant_id} for user {email}...")
            
            if check_shopify_stock(variant_id):
                # Product is IN STOCK!
                print(f"Stock found! Notifying {email}...")
                
                # 2. Send in-stock notification email
                notification_subject = "🎉 IN STOCK NOW! Your desired product is ready!"
                notification_body = (
                    f"Great news, {email}! The product you were waiting for "
                    "is officially back in stock! \n\n"
                    "Don't miss out, buy now:\n"
                    # NOTE: You MUST replace this with the actual product URL template
                    "https://YOUR_STORE_NAME.myshopify.com/products/PRODUCT_HANDLE" 
                )
                
                if send_email(email, notification_subject, notification_body):
                    notified_emails.append(email) # Mark for removal

        # Safely remove notified customers from the waitlist
        for email in notified_emails:
            if email in waitlist:
                del waitlist[email]
                print(f"Removed {email} from waitlist after successful notification.")


# --- Run Application ---
if __name__ == '__main__':
    # Start the background stock checking thread
    stock_thread = Thread(target=stock_checker_task)
    # Allows thread to exit when the main program exits
    stock_thread.daemon = True 
    stock_thread.start()
    
    # Listen on all public IPs on port 8080 (Common for Render/Gunicorn)
    # Note: When deploying with Gunicorn, this block is usually bypassed.
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080))
