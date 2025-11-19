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

# --- Configuration: Reads from Environment Variables (No Hardcoded API Key Default) ---
try:
    # IMPORTANT: The Shopify API Key should be set securely in Render environment variables.
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com") 
    
    # !!! WARNING: Removed the hardcoded key here. Ensure this is set in Render ENV vars!
    SHOPIFY_API_KEY = os.environ.get("5d9f422c303e02187b2442b1b68edf6a") 
    
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj") # App Password
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10") 
    
    # Safely construct base URL for storefront links
    storefront_base_url_env = os.environ.get("STOREFRONT_BASE_URL")
    if storefront_base_url_env:
        STOREFRONT_BASE_URL = storefront_base_url_env.rstrip('/')
    else:
        STOREFRONT_BASE_URL = f"https://{SHOPIFY_STORE_URL}".rstrip('/')
    
    # MongoDB Configuration 
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?appName=PadhaiOn")

except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. {e}")
    

app = Flask(__name__)

# Initialize MongoDB Client (No Change)
waitlist_collection = None
try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['shopify_waitlist_db'] 
    waitlist_collection = db['waitlist_entries']
    waitlist_collection.create_index([("email", 1), ("variant_id", 1)], unique=True)
    print("Successfully connected to MongoDB and initialized database.")
except (ServerSelectionTimeoutError, PyMongoError, TimeoutError) as e:
    print(f"ERROR: Could not connect to MongoDB. Please check MONGODB_URI/password/DB name. Error: {e}")

# Configure CORS (No Change)
if STOREFRONT_BASE_URL:
    CORS(app, resources={r"/*": {"origins": STOREFRONT_BASE_URL}})
else:
    CORS(app) 

# --- Database Helpers (No Change) ---

def is_subscribed(email, variant_id):
    """Checks if a customer is already subscribed for a specific variant."""
    if waitlist_collection is None: return False 
    try:
        return waitlist_collection.find_one({'email': email, 'variant_id': str(variant_id)}) is not None
    except PyMongoError as e:
        print(f"DB Error checking subscription: {e}")
        return False


def add_waitlist_entry(email, variant_id):
    """Adds or updates a waitlist entry, ensuring uniqueness."""
    if waitlist_collection is None: 
        print("DB Not Connected.")
        return False
    try:
        waitlist_collection.update_one(
            {'email': email, 'variant_id': str(variant_id)},
            {'$set': {'timestamp': time.time()}},
            upsert=True
        )
        return True
    except PyMongoError as e:
        print(f"DB Error adding entry: {e}")
        return False

def get_waitlist_entries():
    """Retrieves all unique variant IDs and the emails waiting for them."""
    if waitlist_collection is None: 
        return {}
    
    try:
        pipeline = [
            {
                '$group': {
                    '_id': '$variant_id',
                    'emails': {'$addToSet': '$email'}
                }
            }
        ]
        results = list(waitlist_collection.aggregate(pipeline))
        waitlist_map = {item['_id']: item['emails'] for item in results}
        return waitlist_map
    except PyMongoError as e:
        print(f"DB Error fetching waitlist: {e}")
        return {}


def remove_waitlist_entry(email, variant_id):
    """Removes a customer from a specific product's waitlist."""
    if waitlist_collection is None: return False 
    try:
        waitlist_collection.delete_one({'email': email, 'variant_id': str(variant_id)})
        return True
    except PyMongoError as e:
        print(f"DB Error removing entry: {e}")
        return False

# --- Shopify API Helper (Improved Error Logging) ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY: 
        print("❌ ERROR: Shopify credentials missing. Cannot check stock.")
        # If credentials are missing, we cannot proceed.
        return False
    
    # Robustly extract numeric ID (No Change)
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
        
        response.raise_for_status() # Raises HTTPError for 4xx/5xx status codes
        
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

# --- Email Helper (No Change) ---
def send_email(to_email, subject, body):
    """Sends an email using the configured SMTP settings."""
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

# --- Endpoints (No Change) ---

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


@app.route('/notify-signup', methods=['POST'])
def notify_signup():
    """Handles the user sign-up request from the Shopify Liquid template."""
    try:
        if request.content_type != 'application/json':
             return jsonify({"error": "Content-Type must be application/json."}), 415

        data = request.get_json()
        email = data.get('email')
        variant_id = data.get('variant_id')

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        # Check if already subscribed to prevent redundant processing/emails
        if is_subscribed(email, variant_id):
            return jsonify({"message": "You are already subscribed to the waitlist for this product."}), 200

        # Add user to the MongoDB waitlist
        if add_waitlist_entry(email, variant_id):
            # Send initial confirmation email
            initial_subject = "✅ You're on the Waitlist!"
            initial_body = (
                f"Thanks! We've added your email, {email}, to the notification list for product variant {variant_id}. "
                "We will send you a second email the moment the item is back in stock."
            )
            send_email(email, initial_subject, initial_body)

            return jsonify({"message": "Successfully added to the waitlist. Confirmation email sent."}), 200
        else:
             return jsonify({"error": "Failed to save entry to database."}), 500
        
    except Exception as e:
        print(f"Error processing sign-up request: {e}")
        return jsonify({"error": "Internal server error during processing."}), 500


# --- Background Stock Checker (Set to 5 minutes for stability) ---
def stock_checker_task():
    """Background task to periodically check stock and send notifications."""
    print("Stock checker thread started.")
    
    time.sleep(5) 
    
    # 5 minutes (300 seconds) is the recommended minimum for Shopify API stability.
    # Change to 5 if you insist on 5 seconds, but expect rate limiting.
    CHECK_INTERVAL_SECONDS = 300 
    
    while True:
        start_time = time.time()
        print(f"--- Starting stock check cycle at {time.ctime(start_time)} ---")
        
        waitlist_map = get_waitlist_entries()
        print(f"Checking waitlist for {len(waitlist_map)} unique variants.")
        
        notified_list = []

        for variant_id, emails in waitlist_map.items():
            
            # Check the Shopify API
            if check_shopify_stock(variant_id):
                print(f"Variant {variant_id} is IN STOCK. Notifying {len(emails)} customers.")
                
                notification_subject = "🎉 IN STOCK NOW! Buy Before It Sells Out!"
                
                for email in emails:
                    notification_body = (
                        f"Great news, {email}! The product you were waiting for "
                        f"is officially back in stock! Variant ID: {variant_id}.\n\n"
                        "Don't wait, buy it here: "
                        f"{STOREFRONT_BASE_URL}/cart/{variant_id}:1" 
                        "\n\nNote: This link adds one item directly to your cart."
                    )
                    
                    if send_email(email, notification_subject, notification_body):
                        notified_list.append((email, variant_id))
                    else:
                        print(f"⚠️ WARNING: Failed to send notification email to {email} for variant {variant_id}. (Check SMTP logs above)")


        # Safely remove notified customers from the database
        for email, variant_id in notified_list:
            if remove_waitlist_entry(email, variant_id):
                 print(f"🗑️ Successfully removed {email} for variant {variant_id} from the waitlist.")
            else:
                 print(f"⚠️ WARNING: Failed to remove {email} for variant {variant_id} from the waitlist.")
        
        end_time = time.time()
        duration = end_time - start_time
        print(f"--- Stock check cycle complete. {len(notified_list)} notifications sent. Duration: {duration:.2f}s ---")
        
        # Calculate remaining sleep time to maintain the interval
        sleep_duration = CHECK_INTERVAL_SECONDS - duration
        if sleep_duration > 0:
            print(f"😴 Sleeping for {sleep_duration:.0f} seconds.")
            time.sleep(sleep_duration)
        else:
            print(f"⚠️ WARNING: Stock check took longer than {CHECK_INTERVAL_SECONDS} seconds. Running next cycle immediately.")
            time.sleep(5) 


# --- Run Application (No Change) ---
if __name__ == '__main__':
    if waitlist_collection is not None:
        if not any(t.name == 'StockCheckerThread' for t in threading.enumerate()):
            stock_thread = threading.Thread(target=stock_checker_task, name='StockCheckerThread')
            stock_thread.daemon = True 
            stock_thread.start()
    else:
        print("WARNING: Stock checker not started due to MongoDB connection failure.")
    
    app.run(host='00.0.0', port=os.environ.get('PORT', 8080))

