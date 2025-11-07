import os
import requests
import json
import smtplib
from email.mime.text import MIMEText
import threading 
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError 
from datetime import datetime
import re 

# --- Configuration: Reads from Environment Variables ---
try:
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com") 
    
    # !!! WARNING: Ensure SHOPIFY_API_KEY (Access Token) is set in Render ENV vars!
    SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY", "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") 
    
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    # CRITICAL: This MUST be a Gmail App Password, not a regular password.
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj") 
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10") 
    
    # Safely construct base URL for storefront links
    STOREFRONT_BASE_URL = f"https://{SHOPIFY_STORE_URL}".rstrip('/')
    
    # MongoDB Configuration 
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?appName=PadhaiOn")

except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. {e}")
    exit(1)
    

app = Flask(__name__)

# Initialize MongoDB Client
waitlist_collection = None
try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['shopify_waitlist_db'] 
    waitlist_collection = db['waitlist_entries']
    waitlist_collection.create_index([("email", 1), ("variant_id", 1)], unique=True)
    print("Successfully connected to MongoDB and initialized database.")
except (ServerSelectionTimeoutError, PyMongoError) as e:
    print(f"❌ ERROR: Could not connect to MongoDB. Error: {e}")

# Configure CORS
CORS(app, resources={r"/*": {"origins": STOREFRONT_BASE_URL}})


# --- Database Helpers (Unchanged Logic) ---

def is_subscribed(email, variant_id):
    if waitlist_collection is None: return False 
    try:
        return waitlist_collection.find_one({'email': email, 'variant_id': str(variant_id)}) is not None
    except PyMongoError as e:
        print(f"DB Error checking subscription: {e}")
        return False


def add_waitlist_entry(email, variant_id):
    if waitlist_collection is None: 
        print("DB Not Connected.")
        return False
    try:
        waitlist_collection.update_one(
            {'email': email, 'variant_id': str(variant_id)},
            {'$set': {'timestamp': datetime.now()}},
            upsert=True
        )
        return True
    except PyMongoError as e:
        print(f"DB Error adding entry: {e}")
        return False

def get_waitlist_entries():
    if waitlist_collection is None: 
        return {}
    
    try:
        pipeline = [
            {'$group': {'_id': '$variant_id', 'emails': {'$addToSet': '$email'}}}
        ]
        results = list(waitlist_collection.aggregate(pipeline))
        waitlist_map = {item['_id']: item['emails'] for item in results}
        return waitlist_map
    except PyMongoError as e:
        print(f"DB Error fetching waitlist: {e}")
        return {}


def remove_waitlist_entry(email, variant_id):
    if waitlist_collection is None: return False 
    try:
        waitlist_collection.delete_one({'email': email, 'variant_id': str(variant_id)})
        return True
    except PyMongoError as e:
        print(f"DB Error removing entry: {e}")
        return False

# --- Shopify API Helper (Unchanged Logic) ---
def check_shopify_stock(variant_id):
    """Fetches the inventory quantity for a specific product variant."""
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
    except requests.exceptions.RequestException as e:
        print(f"❌ Shopify API Request Error checking variant {variant_id}. Error: {e}")
        return False

# --- Email Helper (Modified Logic for detailed logging) ---
def send_email(to_email, subject, body):
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        print("❌ Email configuration missing.")
        return False
    
    # Confirmation that the function was entered
    print(f"Attempting to send email from {EMAIL_ADDRESS} to {to_email}...")
        
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
    except smtplib.SMTPAuthenticationError:
        # Specific error for wrong credentials (most likely App Password issue)
        print(f"❌ Email sending failed to {to_email}: Details: SMTP Authentication Error. CRITICAL: Check if you are using a **Gmail App Password**.")
        return False
    except Exception as e:
        # General connection error
        print(f"❌ Email sending failed to {to_email}: Details: General SMTP Error: {e}")
        return False

# --- Endpoints (Modified Logic to reflect email status) ---

@app.route('/', methods=['GET'])
def home():
    return "Shopify Waitlist Service (Polling-Based) is running.", 200

@app.route('/check-subscription', methods=['GET'])
def check_subscription():
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
    try:
        if request.content_type != 'application/json':
            return jsonify({"error": "Content-Type must be application/json."}), 415

        data = request.get_json()
        email = data.get('email')
        variant_id = data.get('variant_id')

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        if is_subscribed(email, variant_id):
            return jsonify({"message": "You are already subscribed to the waitlist for this product."}), 200

        if add_waitlist_entry(email, variant_id):
            initial_subject = "✅ You're on the Waitlist!"
            initial_body = (
                f"Thanks! We've added your email, {email}, to the notification list for product variant {variant_id}. "
                "We will send you a second email the moment the item is back in stock."
            )
            
            # Check the return status of send_email
            email_sent = send_email(email, initial_subject, initial_body)

            if email_sent:
                return jsonify({"message": "Successfully added to the waitlist. Confirmation email sent."}), 200
            else:
                # Still 200 since the user is subscribed, but warn them the confirmation email failed.
                return jsonify({
                    "message": "Successfully added to the waitlist.", 
                    "warning": "Failed to send confirmation email due to server configuration issue. You are still subscribed for the stock alert, but please check your email configuration."
                }), 200
        else:
            return jsonify({"error": "Failed to save entry to database."}), 500
            
    except Exception as e:
        print(f"Error processing sign-up request: {e}")
        return jsonify({"error": "Internal server error during processing."}), 500


# --- Background Stock Checker (The core automation) ---
def stock_checker_task():
    print("Stock checker thread started.")
    
    time.sleep(5) 
    
    # Keep the recommended 5 minute interval (300 seconds)
    CHECK_INTERVAL_SECONDS = 300 
    
    while True:
        start_time = time.time()
        print(f"--- Starting stock check cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        
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
                        f"(Variant ID: {variant_id}) is officially back in stock!\n\n"
                        f"Buy it here: {STOREFRONT_BASE_URL}/cart/{variant_id}:1" 
                        "\n\nNote: This link adds one item directly to your cart."
                    )
                    
                    if send_email(email, notification_subject, notification_body):
                        notified_list.append((email, variant_id))
                    else:
                        print(f"⚠️ WARNING: Failed to send notification email to {email} for variant {variant_id}. This customer remains on the waitlist.")


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


# --- Run Application ---
if __name__ == '__main__':
    if waitlist_collection is not None:
        if not any(t.name == 'StockCheckerThread' for t in threading.enumerate()):
            stock_thread = threading.Thread(target=stock_checker_task, name='StockCheckerThread')
            stock_thread.daemon = True 
            stock_thread.start()
    else:
        print("WARNING: Stock checker not started due to MongoDB connection failure.")
    
    # Use environment variable PORT (standard for deployment)
    port = int(os.environ.get("PORT", 8080))
    # Change host to '0.0.0.0' for deployment environments like Render/Heroku
    app.run(host='0.0.0.0', port=port)
