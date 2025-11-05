from flask import Flask, request, jsonify
import json
import requests
import smtplib
from email.mime.text import MIMEText
from threading import Thread
import time

# --- Configuration ---
# REPLACE THESE WITH YOUR ACTUAL CREDENTIALS
SHOPIFY_STORE_URL = "YOUR_STORE_NAME.myshopify.com"
SHOPIFY_API_KEY = "YOUR_PRIVATE_APP_API_KEY"
PRODUCT_VARIANT_ID = "YOUR_PRODUCT_VARIANT_ID" # E.g., The specific variant ID for the shoe
SHOPIFY_API_VERSION = "2023-10" # Use a stable API version

# Email Credentials (Use a service like SendGrid, Mailgun, or standard SMTP)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = "your_notifications_email@example.com"
EMAIL_PASSWORD = "your_email_password" # Use an App Password for services like Gmail

app = Flask(__name__)

# Simple in-memory storage for demonstration (USE A REAL DATABASE IN PRODUCTION)
# Format: {email: product_variant_id}
waitlist = {}

# --- Shopify API Helper ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
    url = (
        f"https://{SHOPIFY_API_KEY}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{variant_id}.json"
    )
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # Raise an HTTPError for bad responses
        data = response.json()
        inventory_quantity = data['variant']['inventory_quantity']
        return inventory_quantity > 0
    except requests.exceptions.RequestException as e:
        print(f"Shopify API Error: {e}")
        return False

# --- Email Helper ---
def send_email(to_email, subject, body):
    """Sends an email using the configured SMTP settings."""
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls() # Secure the connection
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
            print(f"Email sent successfully to {to_email}")
            return True
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False

# --- Endpoints ---

@app.route('/notify-signup', methods=['POST'])
def notify_signup():
    """Endpoint for users to sign up to the waitlist."""
    data = request.get_json()
    email = data.get('email')
    variant_id = data.get('variant_id') # Get the product ID from the front-end

    if not email or not variant_id:
        return jsonify({"message": "Missing email or product ID"}), 400

    waitlist[email] = variant_id
    
    # Send initial confirmation email
    initial_subject = "✅ You're on the Waitlist!"
    initial_body = (
        "Thanks for signing up! We'll let you know the moment the product "
        "is back in stock. Product ID: " + variant_id
    )
    send_email(email, initial_subject, initial_body)

    return jsonify({"message": "Successfully added to the waitlist. Confirmation email sent."}), 200

# --- Background Stock Checker ---

def stock_checker_task():
    """Background task to periodically check stock and send notifications."""
    global waitlist
    while True:
        # Check stock every 5 minutes (adjust as needed)
        time.sleep(300) 
        
        # Create a list of emails to remove after sending notification
        notified_emails = [] 
        
        for email, variant_id in list(waitlist.items()):
            if check_shopify_stock(variant_id):
                # Product is IN STOCK!
                notification_subject = "🚨 Product Back In Stock! Buy Now!"
                notification_body = (
                    f"Great news! The product you were waiting for (ID: {variant_id}) "
                    "is back in stock. Don't wait, buy it here: "
                    # Replace with your actual product link
                    "https://YOUR_STORE_NAME.myshopify.com/products/..." 
                )
                
                if send_email(email, notification_subject, notification_body):
                    notified_emails.append(email) # Mark for removal

        # Remove notified customers from the waitlist
        for email in notified_emails:
            if email in waitlist:
                del waitlist[email]
                print(f"Removed {email} from waitlist after notification.")

# --- Run Application ---

if __name__ == '__main__':
    # Start the background stock checking thread
    stock_thread = Thread(target=stock_checker_task)
    stock_thread.daemon = True # Allows thread to exit when the main program exits
    stock_thread.start()
    
    # Run the Flask app (Render will use Gunicorn/similar to run this)
    app.run(debug=True, host='0.0.0.0', port=5000)
