import os
import requests
import json
import smtplib
import threading
import time
import re
import hmac
import hashlib
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, Response, abort
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
from functools import wraps

# --- Configuration: Reads from Environment Variables ---
try:
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com")
    SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY", "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")
    
    # --- !!! NEW AND CRITICAL !!! ---
    # You get this from your Shopify Admin: Settings > Notifications > Webhooks
    # It's the "signing key" shown after you create a webhook.
    SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "YOUR_REAL_WEBHOOK_SECRET_KEY")
    # -----------------------------------

    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj") # Gmail App Password
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10")
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?appName=PadhaiOn")

    # Storefront URL for links
    STOREFRONT_BASE_URL = f"https://{SHOPIFY_STORE_URL.rstrip('/')}"
    # Admin API base URL
    SHOPIFY_ADMIN_API_BASE_URL = (
        f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
    )

except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. {e}")
    exit(1)

# --- Jinja2 Environment Setup ---
CONFIRMATION_TEMPLATE = None
ALERT_TEMPLATE = None
try:
    template_loader = FileSystemLoader(searchpath="./")
    jinja_env = Environment(
        loader=template_loader,
        autoescape=select_autoescape(['html', 'xml'])
    )
    CONFIRMATION_TEMPLATE = jinja_env.get_template("email_confirmation_template.html")
    ALERT_TEMPLATE = jinja_env.get_template("email_alert_template.html")
    print("✅ Successfully loaded email templates.")
except Exception as e:
    print(f"⚠️ WARNING: Could not load email templates. Emails will be plain text. Error: {e}")


app = Flask(__name__)

# --- MongoDB Initialization ---
waitlist_collection = None
try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['shopify_waitlist_db']
    waitlist_collection = db['waitlist_entries']
    # --- !!! UPDATED INDEX !!! ---
    # We now index by inventory_item_id for fast webhook lookups
    waitlist_collection.create_index([("inventory_item_id", 1)])
    waitlist_collection.create_index([("email", 1), ("variant_id", 1)], unique=True)
    print("✅ Successfully connected to MongoDB.")
except (ServerSelectionTimeoutError, PyMongoError) as e:
    print(f"❌ ERROR: Could not connect to MongoDB. Service will not work. Error: {e}")

# --- CORS Configuration ---
CORS(app, resources={r"/*": {"origins": STOREFRONT_BASE_URL}})


# --- Webhook Security (HMAC Verification) ---
def verify_shopify_webhook(f):
    """Decorator to verify incoming webhooks from Shopify."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Get the signature from the request header
        hmac_header = request.headers.get('X-Shopify-Hmac-Sha256')
        if not hmac_header:
            print("❌ Webhook Error: Missing X-Shopify-Hmac-Sha256 header.")
            abort(401)

        # 2. Get the raw request body
        data = request.get_data()

        # 3. Verify the signature
        try:
            secret_bytes = SHOPIFY_WEBHOOK_SECRET.encode('utf-8')
            digest = hmac.new(secret_bytes, data, hashlib.sha256).digest()
            computed_hmac = base64.b64encode(digest)

            if not hmac.compare_digest(computed_hmac, hmac_header.encode('utf-8')):
                print("❌ Webhook Error: Invalid HMAC signature.")
                abort(401)
                
        except Exception as e:
            print(f"❌ Webhook Error: HMAC comparison failed. {e}")
            abort(401)
        
        # 4. Pass the raw body data to the function
        request.webhook_data = data
        return f(*args, **kwargs)
    return decorated_function


# --- Database Helpers ---
def is_subscribed(email, variant_id):
    if waitlist_collection is None: return False
    try:
        return waitlist_collection.find_one({'email': email, 'variant_id': str(variant_id)}) is not None
    except PyMongoError as e:
        print(f"DB Error checking subscription: {e}")
        return False

# --- !!! UPDATED FUNCTION !!! ---
def add_waitlist_entry(email, variant_id, inventory_item_id):
    """Adds a new entry to the waitlist, now including the inventory_item_id."""
    if waitlist_collection is None:
        print("DB Not Connected.")
        return False
    try:
        waitlist_collection.update_one(
            {'email': email, 'variant_id': str(variant_id)},
            {'$set': {
                'timestamp': datetime.now(),
                'inventory_item_id': str(inventory_item_id) # Store this for the webhook
            }},
            upsert=True
        )
        return True
    except PyMongoError as e:
        print(f"DB Error adding entry: {e}")
        return False

def get_waitlist_entries_by_inventory_id(inventory_item_id):
    """Finds all users waiting for a specific inventory item."""
    if waitlist_collection is None:
        return []
    try:
        # Find all documents matching the inventory_item_id
        entries = waitlist_collection.find({'inventory_item_id': str(inventory_item_id)})
        return list(entries)
    except PyMongoError as e:
        print(f"DB Error fetching waitlist by inventory_id: {e}")
        return []

def remove_waitlist_entry(email, variant_id):
    if waitlist_collection is None: return False
    try:
        waitlist_collection.delete_one({'email': email, 'variant_id': str(variant_id)})
        return True
    except PyMongoError as e:
        print(f"DB Error removing entry: {e}")
        return False

# --- Shopify API Helpers ---
def _get_numeric_variant_id(variant_id_str):
    variant_id_str = str(variant_id_str)
    match = re.search(r'\d+$', variant_id_str)
    numeric_id = match.group(0) if match else variant_id_str
    if not numeric_id.isdigit():
        return None
    return numeric_id

def _make_shopify_api_request(url):
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY:
        print("❌ ERROR: Shopify credentials missing.")
        return None
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_API_KEY
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Shopify API Request Error: {e}")
        return None

# --- !!! UPDATED FUNCTION !!! ---
def get_variant_details_for_signup(variant_id):
    """
    Fetches the variant details on signup to get the inventory_item_id.
    """
    numeric_id = _get_numeric_variant_id(variant_id)
    if not numeric_id:
        return None

    # We only need the inventory_item_id from the variant
    url = f"{SHOPIFY_ADMIN_API_BASE_URL}/variants/{numeric_id}.json?fields=inventory_item_id"
    data = _make_shopify_api_request(url)
    
    if data and 'variant' in data and 'inventory_item_id' in data['variant']:
        return data['variant']
        
    print(f"Could not verify variant for signup: {numeric_id}.")
    return None

def get_product_details_for_notification(variant_id):
    """Fetches all product/variant details needed for the email template."""
    numeric_id = _get_numeric_variant_id(variant_id)
    if not numeric_id:
        return None

    variant_url = f"{SHOPIFY_ADMIN_API_BASE_URL}/variants/{numeric_id}.json?fields=product_id,title"
    variant_data = _make_shopify_api_request(variant_url)
    
    if not variant_data or 'variant' not in variant_data:
        return None

    product_id = variant_data['variant']['product_id']
    variant_title = variant_data['variant']['title']

    product_url = f"{SHOPIFY_ADMIN_API_BASE_URL}/products/{product_id}.json?fields=title,handle"
    product_data = _make_shopify_api_request(product_url)

    if not product_data or 'product' not in product_data:
        return None

    return {
        "product_title": product_data['product']['title'],
        "variant_title": variant_title,
        "product_handle": product_data['product']['handle'],
        "store_url": STOREFRONT_BASE_URL
    }

# --- Email Helper (Unchanged) ---
def send_email(to_email, subject, text_body, html_body=None):
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        print("❌ Email configuration missing.")
        return False
    print(f"Attempting to send email from {EMAIL_ADDRESS} to {to_email}...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    msg.attach(MIMEText(text_body, 'plain'))
    if html_body:
        msg.attach(MIMEText(html_body, 'html'))
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
            print(f"📧 Email sent successfully to {to_email}")
            return True
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        return False

# --- API Endpoints ---

@app.route('/', methods=['GET'])
def home():
    return "Shopify Waitlist Service (Webhook-Based) is running.", 200

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

# --- !!! UPDATED ENDPOINT !!! ---
@app.route('/notify-signup', methods=['POST'])
def notify_signup():
    try:
        data = request.get_json()
        if not data:
             return jsonify({"error": "Invalid JSON payload."}), 400

        email = data.get('email')
        variant_id = data.get('variant_id')

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400
        
        numeric_id = _get_numeric_variant_id(variant_id)
        if not numeric_id:
            return jsonify({"error": "Invalid variant ID format."}), 400

        if is_subscribed(email, numeric_id):
            return jsonify({"message": "You are already subscribed to this waitlist."}), 200
        
        # --- NEW STEP: Get inventory_item_id ---
        variant_data = get_variant_details_for_signup(numeric_id)
        if not variant_data:
            print(f"Failed to get inventory_item_id for variant {numeric_id}")
            return jsonify({"error": "Could not find variant details."}), 404
        
        inventory_item_id = variant_data.get('inventory_item_id')
        # ----------------------------------------

        if add_waitlist_entry(email, numeric_id, inventory_item_id):
            initial_subject = "✅ You're on the Waitlist!"
            text_body = (
                f"Thanks! We've added your email, {email}, to the notification list for product variant {numeric_id}. "
                "We will send you a second email the moment the item is back in stock."
            )
            html_body = None

            if CONFIRMATION_TEMPLATE:
                try:
                    html_body = CONFIRMATION_TEMPLATE.render(
                        email_address=email,
                        variant_id=numeric_id,
                        store_url=STOREFRONT_BASE_URL
                    )
                except Exception as e:
                    print(f"Warning: Failed to render confirmation template: {e}")

            email_sent = send_email(email, initial_subject, text_body, html_body)

            if email_sent:
                return jsonify({"message": "Successfully added to waitlist. Confirmation email sent."}), 200
            else:
                return jsonify({
                    "message": "Successfully added to waitlist.",
                    "warning": "Failed to send confirmation email due to server config issue."
                }), 200
        else:
            return jsonify({"error": "Failed to save entry to database."}), 500

    except Exception as e:
        print(f"Error in /notify-signup: {e}")
        return jsonify({"error": "Internal server error."}), 500


# --- !!! NEW WEBHOOK RECEIVER !!! ---
@app.route('/shopify-webhook-receiver', methods=['POST'])
@verify_shopify_webhook
def shopify_webhook_receiver():
    """
    This endpoint receives the 'inventory_levels/update' webhook from Shopify.
    It verifies the request and then processes the notification.
    """
    try:
        # request.webhook_data was added by the @verify_shopify_webhook decorator
        payload = json.loads(request.webhook_data.decode('utf-8'))
        
        # 1. Check if the product is back in stock
        available_quantity = payload.get('available', 0)
        if available_quantity > 0:
            inventory_item_id = payload.get('inventory_item_id')
            print(f"Webhook Received: Inventory item {inventory_item_id} is IN STOCK ({available_quantity}).")
            
            # 2. Start a new thread to handle notifications
            # This lets us send the "200 OK" response back to Shopify immediately.
            notification_thread = threading.Thread(
                target=process_notifications_for_item, 
                args=(str(inventory_item_id),)
            )
            notification_thread.start()
        
        else:
            # Stock was updated, but still 0 or less.
            inventory_item_id = payload.get('inventory_item_id')
            print(f"Webhook Received: Stock update for {inventory_item_id}, but still out of stock ({available_quantity}). No action needed.")

    except Exception as e:
        print(f"❌ Error processing webhook payload: {e}")
        # Still return 200 so Shopify stops retrying
        
    # IMPORTANT: Always return a 200 OK to Shopify immediately.
    return jsonify({"status": "received"}), 200


# --- !!! NEW NOTIFICATION PROCESSOR !!! ---
def process_notifications_for_item(inventory_item_id):
    """
    (Runs in a background thread)
    Fetches all users for an item, sends emails, and removes them from the waitlist.
    """
    print(f"Thread started: Processing notifications for inventory item {inventory_item_id}")
    
    # 1. Get all users waiting for this item
    waitlist_entries = get_waitlist_entries_by_inventory_id(inventory_item_id)
    if not waitlist_entries:
        print(f"No users found on waitlist for item {inventory_item_id}.")
        return

    print(f"Found {len(waitlist_entries)} users for item {inventory_item_id}. Fetching product details...")
    
    # 2. Get product details (only needs to be done once)
    # We can get the variant_id from the first entry, as they all share it
    # (or rather, they all map to the same item)
    variant_id = waitlist_entries[0]['variant_id']
    details = get_product_details_for_notification(variant_id)
    
    if not details:
        print(f"⚠️ WARNING: Failed to fetch product details for variant {variant_id}. Cannot send notifications.")
        return

    notification_subject = "🎉 IN STOCK NOW! Your Item is Back!"
    notified_list = []

    # 3. Loop through and send emails
    for entry in waitlist_entries:
        email = entry['email']
        
        text_body = (
            f"Great news, {email}!\n\n"
            f"The product you were waiting for is officially back in stock:\n"
            f"Product: {details['product_title']}\n"
            f"Variant: {details['variant_title']}\n\n"
            f"Buy it here before it sells out again:\n"
            f"{details['store_url']}/products/{details['product_handle']}"
        )
        
        html_body = None
        if ALERT_TEMPLATE:
            try:
                html_body = ALERT_TEMPLATE.render(
                    product_title=details['product_title'],
                    variant_title=details['variant_title'],
                    product_handle=details['product_handle'],
                    store_url=details['store_url']
                )
            except Exception as e:
                 print(f"Warning: Failed to render alert template for {email}: {e}")
        
        if send_email(email, notification_subject, text_body, html_body):
            notified_list.append(entry)
        else:
            print(f"⚠️ WARNING: Failed to send notification to {email} for variant {variant_id}. They remain on the list.")

    # 4. Safely remove notified customers
    for entry in notified_list:
        if remove_waitlist_entry(entry['email'], entry['variant_id']):
            print(f"🗑️ Successfully removed {entry['email']} for variant {entry['variant_id']} from waitlist.")
        else:
            print(f"⚠️ WARNING: Failed to remove {entry['email']} from waitlist.")
    
    print(f"Thread finished: Notifications complete for inventory item {inventory_item_id}")


# --- Run Application ---
if __name__ == '__main__':
    if waitlist_collection is None:
        print("❌ FATAL: MongoDB not connected. Application cannot start correctly.")
    else:
        port = int(os.environ.get("PORT", 8080))
        print(f"Starting Flask server on host 0.0.0.0, port {port}")
        # Note: We no longer start the stock_checker_task thread!
        app.run(host='0.0.0.0', port=port)
