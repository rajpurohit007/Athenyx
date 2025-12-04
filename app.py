from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import smtplib
from email.mime.text import MIMEText
import threading 
import time
import os
import json
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError 
from socket import timeout as TimeoutError 
import re 
from pywebpush import webpush, WebPushException # 🔔 NEW IMPORT

# --- Configuration: Reads from Environment Variables ---
try:
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com") 
    SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY") # Ensure this is set in your Render ENV vars!
    
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj") # Gmail App Password
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10") 
    
    # MongoDB Configuration 
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?appName=PadhaiOn")
    
    # 🔔 VAPID Keys for Push Notifications
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:your_contact_email@example.com")

    # Safely construct base URL for storefront links
    storefront_base_url_env = os.environ.get("STOREFRONT_BASE_URL")
    if storefront_base_url_env:
        STOREFRONT_BASE_URL = storefront_base_url_env.rstrip('/')
    else:
        STOREFRONT_BASE_URL = f"https://{SHOPIFY_STORE_URL}".rstrip('/')

    if not SHOPIFY_API_KEY:
        print("❌ WARNING: SHOPIFY_API_KEY is missing. Stock checker will fail.")
    if not VAPID_PUBLIC_KEY:
        print("❌ WARNING: VAPID keys are missing. Push notifications disabled.")

except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. {e}")
    

app = Flask(__name__)

# Initialize MongoDB Client
waitlist_collection = None
try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['shopify_waitlist_db'] 
    waitlist_collection = db['waitlist_entries']
    
    # Ensure push_subscription is part of the schema/index optimization
    waitlist_collection.create_index([("email", 1), ("variant_id", 1)], unique=True)
    waitlist_collection.create_index([("variant_id", 1)])
    
    print("Successfully connected to MongoDB and initialized database.")
except (ServerSelectionTimeoutError, PyMongoError, TimeoutError) as e:
    print(f"ERROR: Could not connect to MongoDB. Error: {e}")

# Configure CORS
# NOTE: Using environment variable for security, defaults to allow any if not set.
CORS(app, resources={r"/*": {"origins": os.environ.get("FRONTEND_ORIGIN", "*")}}) 

# --- Database Helpers (UPDATED for Push Subscription) ---

def is_subscribed(email, variant_id):
    """Checks if a customer is already subscribed for a specific variant."""
    if waitlist_collection is None: return False 
    try:
        return waitlist_collection.find_one({'email': email, 'variant_id': str(variant_id)}) is not None
    except PyMongoError as e:
        print(f"DB Error checking subscription: {e}")
        return False


def add_waitlist_entry(email, variant_id, push_subscription=None):
    if waitlist_collection is None:
        print("DB Not Connected.")
        return False

    try:
        update_fields = {
            "timestamp": time.time(),
            "email": email,
            "variant_id": str(variant_id)
        }

        # Store push subscription if valid
        if push_subscription and isinstance(push_subscription, dict) and "endpoint" in push_subscription:
            update_fields["push_subscription"] = push_subscription

        waitlist_collection.update_one(
            {"email": email, "variant_id": str(variant_id)},
            {"$set": update_fields},
            upsert=True
        )
        return True

    except PyMongoError as e:
        print(f"DB Error adding entry: {e}")
        return False


def get_waitlist_entries():
    """Retrieves all unique variants and the entries waiting for them."""
    if waitlist_collection is None: 
        return []
    
    try:
        # Retrieve all entries with push subscriptions included
        return list(waitlist_collection.find())
    except PyMongoError as e:
        print(f"DB Error fetching waitlist: {e}")
        return []


def remove_waitlist_entry(email, variant_id):
    """Removes a customer from a specific product's waitlist."""
    if waitlist_collection is None: return False 
    try:
        waitlist_collection.delete_one({'email': email, 'variant_id': str(variant_id)})
        return True
    except PyMongoError as e:
        print(f"DB Error removing entry: {e}")
        return False

# --- Shopify API Helper (Unchanged) ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
    # (function body remains the same as provided in your input)
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY: 
        print("❌ ERROR: Shopify credentials missing. Cannot check stock.")
        return False
    
    variant_id_str = str(variant_id)
    match = re.search(r'\d+$', variant_id_str)
    numeric_id = match.group(0) if match else variant_id_str

    if not numeric_id.isdigit():
        print(f"❌ ERROR: Could not parse numeric variant ID from {variant_id_str}. Skipping check.")
        return False

    url = (
        f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{numeric_id}.json"
    )
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_API_KEY
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 404:
             print(f"❌ Shopify API Error 404: Variant {numeric_id} not found. Check the ID.")
             return False
        
        response.raise_for_status() 
        
        data = response.json()
        inventory_quantity = data['variant']['inventory_quantity']
        print(f"✅ Stock check for variant {variant_id} (ID: {numeric_id}): {inventory_quantity} available.")
        
        return inventory_quantity > 0
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ Shopify API HTTP Error (Status {response.status_code}) checking variant {variant_id}.")
        print("   -> **ACTION NEEDED:** Check your **SHOPIFY_API_KEY** permissions and value.")
        print(f"   -> Details: {http_err}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Shopify API Request Error checking variant {variant_id}. Error: {e}")
        return False


# --- Email Helper (Unchanged) ---
def send_email(to_email, subject, body):
    # (function body remains the same as provided in your input)
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        print("❌ Email configuration missing.")
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
            print(f"📧 Email sent successfully to {to_email}")
            return True
    except Exception as e:
        print(f"❌ Email sending failed to {to_email}: **Check Gmail App Password** or SMTP settings.")
        print(f"   -> Details: {e}")
        return False

# --- 🔔 NEW Push Notification Helper ---
def send_push_notification(subscription, payload):
    """Sends a push notification to a subscribed browser endpoint."""
    if not all([VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY]):
        # This should have been caught in config warning, but safe to check here
        return False
        
    try:
        # Pywebpush expects the subscription object directly
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIM_EMAIL}
        )
        print(f"🔔 Push notification sent successfully.")
        return True
    except WebPushException as e:
        print(f"❌ Push notification failed (Status {e.response.status_code}): {e.response.text}")
        if e.response.status_code == 410: # Gone/Expired
            print("   -> Subscription is expired (410). Needs to be removed from DB.")
        return False
    except Exception as e:
        print(f"❌ Push notification failed: {e}")
        return False


# --- Background Stock Checker (UPDATED for Push) ---
def stock_checker_task():
    """Background task to periodically check stock and send notifications."""
    print("Stock checker thread started.")
    
    CHECK_INTERVAL_SECONDS = 300 # 5 minutes
    time.sleep(5) 
    
    while True:
        start_time = time.time()
        print(f"--- Starting stock check cycle at {time.ctime(start_time)} ---")
        
        # Changed to fetch all entries, not just unique variants (needed for push subscriptions)
        all_entries = get_waitlist_entries()
        print(f"Checking waitlist for {len(all_entries)} entries.")
        
        notified_list = []
        variants_to_check = {} # Group entries by variant_id for API calls

        for entry in all_entries:
            variant_id = entry.get('variant_id')
            if variant_id not in variants_to_check:
                variants_to_check[variant_id] = []
            variants_to_check[variant_id].append(entry)


        for variant_id, entries in variants_to_check.items():
            
            # Check the Shopify API
            if check_shopify_stock(variant_id):
                
                # --- Notification Content ---
                notification_subject = "🎉 IN STOCK NOW! Buy Before It Sells Out!"
                notification_url = f"{STOREFRONT_BASE_URL}/cart/{variant_id}:1"
                
                for entry in entries:
                    email = entry.get('email')
                    push_subscription = entry.get('push_subscription')
                    
                    email_body = (
                        f"Great news, {email}! The product you were waiting for "
                        f"is officially back in stock! Variant ID: {variant_id}.\n\n"
                        f"Don't wait, buy it here: {notification_url}" 
                        "\n\nNote: This link adds one item directly to your cart."
                    )
                    
                    push_payload = {
                        "title": "🔥 Back in Stock!",
                        "body": f"Your variant ({variant_id}) is available now!",
                        "url": notification_url
                    }
                    
                    email_ok = False
                    push_ok = False
                    
                    # 1. Send Email
                    if send_email(email, notification_subject, email_body):
                        email_ok = True
                    
                    # 2. Send Push Notification
                    if push_subscription:
                        if send_push_notification(push_subscription, push_payload):
                            push_ok = True
                        
                    # If either succeeded, mark for removal
                    if email_ok or push_ok:
                        notified_list.append((email, variant_id))
                        print(f"   -> Notified {email} (Email: {email_ok}, Push: {push_ok})")
                    else:
                        print(f"   -> WARNING: Failed all notifications for {email}.")


        # Safely remove notified customers from the database
        for email, variant_id in set(notified_list): # Use set to ensure unique removal actions
            if remove_waitlist_entry(email, variant_id):
                 print(f"🗑️ Successfully removed {email} for variant {variant_id} from the waitlist.")
            else:
                 print(f"⚠️ WARNING: Failed to remove {email} for variant {variant_id} from the waitlist.")
        
        end_time = time.time()
        duration = end_time - start_time
        print(f"--- Stock check cycle complete. {len(notified_list)} notification attempts made. Duration: {duration:.2f}s ---")
        
        # Calculate remaining sleep time
        sleep_duration = CHECK_INTERVAL_SECONDS - duration
        if sleep_duration > 0:
            print(f"😴 Sleeping for {sleep_duration:.0f} seconds.")
            time.sleep(sleep_duration)
        else:
            print(f"⚠️ WARNING: Stock check took longer than {CHECK_INTERVAL_SECONDS} seconds. Running next cycle immediately.")
            time.sleep(5) 


# --- Endpoints (FIXED VAPID KEY ROUTE) ---

@app.route('/', methods=['GET'])
def home():
    """Simple check for Render health check."""
    return "Shopify Waitlist Service is running.", 200

@app.route('/check-subscription', methods=['GET'])
def check_subscription():
    """Checks subscription status for a logged-in user."""
    email = request.args.get('email')
    variant_id = request.args.get('variant_id')

    if not email or not variant_id:
        return jsonify({"error": "Missing email or variant ID."}), 400

    if is_subscribed(email, variant_id):
        return jsonify({"subscribed": True}), 200
    else:
        return jsonify({"subscribed": False}), 200

# 🔔 NEW ENDPOINT: Serves VAPID Public Key (Fixes 404 Error)
@app.route('/vapid-public-key', methods=['GET'])
def vapid_public_key():
    """Returns the VAPID Public Key for the frontend Service Worker."""
    if not VAPID_PUBLIC_KEY:
        return jsonify({"error": "VAPID Public Key not configured on the server."}), 503
    
    return jsonify({"publicKey": VAPID_PUBLIC_KEY}), 200


@app.route('/notify-signup', methods=['POST'])
def notify_signup():
    """Handles the user sign-up request from the Shopify Liquid template."""
    try:
        if request.content_type != 'application/json':
             return jsonify({"error": "Content-Type must be application/json."}), 415

        data = request.get_json()
        email = data.get('email')
        variant_id = data.get('variant_id')
        push_subscription = data.get('push_subscription') # 🔔 Retrieve push subscription

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        # Check if already subscribed to prevent redundant processing/emails
        is_already_subscribed = is_subscribed(email, variant_id)
        
        # Add or update user to the MongoDB waitlist, including push subscription
        if add_waitlist_entry(email, variant_id, push_subscription):
            
            if not is_already_subscribed:
                # Send initial confirmation email only for new subscriptions
                initial_subject = "✅ You're on the Waitlist!"
                initial_body = (
                    f"Thanks! We've added your email, {email}, to the notification list for variant {variant_id}. "
                    "We will send you a second email the moment the item is back in stock."
                )
                send_email(email, initial_subject, initial_body)
                return jsonify({"message": "Successfully added to the waitlist. Confirmation email sent."}), 200
            else:
                 # Success message for updates
                 return jsonify({"message": "Subscription updated."}), 200
        else:
             return jsonify({"error": "Failed to save entry to database."}), 500
        
    except Exception as e:
        print(f"Error processing sign-up request: {e}")
        return jsonify({"error": "Internal server error during processing."}), 500


# --- Run Application ---
if __name__ == '__main__':
    if waitlist_collection is not None:
        if not any(t.name == 'StockCheckerThread' for t in threading.enumerate()):
            stock_thread = threading.Thread(target=stock_checker_task, name='StockCheckerThread')
            stock_thread.daemon = True 
            stock_thread.start()
    else:
        print("WARNING: Stock checker not started due to MongoDB connection failure.")
    
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 10000))
