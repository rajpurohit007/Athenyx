import os
import requests
import json
import hmac
import hashlib
from flask import Flask, request, jsonify, abort
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from datetime import datetime
import re

# --- Configuration: Reads from Environment Variables ---
try:
    # Use environment variables for secure and flexible configuration
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com") 
    SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "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") 
    SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET", "3c3b8d61c508e9b950ca22a8e91cadc819491c5785dc35780af05002f5ca5e56") 
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2024-10") 
    
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj") # App Password
    
    # Safely construct base URL for storefront links
    STOREFRONT_BASE_URL = f"https://{SHOPIFY_STORE_URL}".rstrip('/')
    
    # MongoDB Configuration 
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?appName=PadhaiOn")

except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. {e}")
    exit(1) # Stop execution if configuration fails

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


# --- SECURITY & UTILITY FUNCTIONS ---

def verify_webhook_hmac(data, hmac_header):
    """Verifies that the incoming request is truly from Shopify."""
    encoded_secret = SHOPIFY_WEBHOOK_SECRET.encode('utf-8')
    digest = hmac.new(encoded_secret, data, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, hmac_header)

def get_subscribers_for_variant(variant_id):
    """Retrieves all unique subscriber emails for a specific variant ID."""
    if waitlist_collection is None: return []
    try:
        subscriptions = waitlist_collection.find(
            {"variant_id": str(variant_id)},
            {"email": 1, "_id": 0} 
        )
        return list(set(doc['email'] for doc in subscriptions))
    except PyMongoError as e:
        print(f"DB Error fetching subscribers: {e}")
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

# --- SHOPIFY API HELPER: Get Product Details ---

def get_product_details_by_variant_id(variant_id):
    """Fetches product/variant details using the Admin REST API."""
    
    # Robustly extract numeric ID from potential GID format
    variant_id_str = str(variant_id)
    match = re.search(r'\d+$', variant_id_str)
    numeric_id = match.group(0) if match else variant_id_str
    if not numeric_id.isdigit(): return None

    url = (
        f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{numeric_id}.json"
    )
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        variant_data = data.get('variant', {})
        product_id = variant_data.get('product_id')
        
        # Need the parent product ID to fetch its details (title and handle)
        if not product_id: return None

        product_url = (
            f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
            f"/products/{product_id}.json"
        )
        product_response = requests.get(product_url, headers=headers, timeout=5)
        product_response.raise_for_status()
        product_data = product_response.json().get('product', {})

        return {
            'product_title': product_data.get('title', 'Restocked Item'),
            'product_handle': product_data.get('handle', ''),
            'variant_title': variant_data.get('title', 'Default')
        }

    except requests.exceptions.RequestException as e:
        print(f"❌ Shopify API (details fetch) failed for variant {variant_id}: {e}")
        return None

# --- EMAIL HELPER ---
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
        print(f"❌ Email sending failed to {to_email}: Details: {e}")
        return False


# --- CORE WEBHOOK ENDPOINT (The solution for instant alerts) ---

@app.route('/webhook/inventory-update', methods=['POST'])
def inventory_webhook():
    """Receives instant inventory update webhooks from Shopify."""
    
    data = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256')

    # 1. SECURITY CHECK
    if not verify_webhook_hmac(data, hmac_header):
        print("SECURITY ALERT: HMAC verification failed.")
        abort(401) # Unauthorized

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        print("Failed to parse JSON payload.")
        abort(400)

    # Note: Shopify sends inventory updates based on 'Inventory Item' or 'Product Update'
    # We will assume a payload that contains the inventory level per location (common for modern hooks)
    
    # The 'Inventory Level Update' webhook is the most direct signal:
    # It contains 'inventory_item_id' and 'available' quantity.
    # However, many apps subscribe to 'products/update' or check the variant via API 
    # based on the inventory_item_id or location_id change notification.
    
    # For simplicity and directness, we will look for 'variant_id' and 'available' (from the old 'inventory_level/update' style, or derive it).
    
    # If using 'Inventory Level Update' (recommended):
    inventory_item_id = payload.get('inventory_item_id')
    available_quantity = payload.get('available') 
    
    if inventory_item_id is None or available_quantity is None:
        # Fallback for simpler testing or older webhooks (adjust based on your actual Shopify webhook setup)
        print("⚠️ WARNING: Webhook payload missing inventory_item_id or available quantity. Skipping.")
        return jsonify({"status": "ok", "message": "Payload missing key data."}), 200

    # 2. Find the corresponding variant_id from the inventory_item_id (Requires an extra API call or DB mapping)
    # The most reliable method is to check the specific variant using the API which also gives us its product_id
    
    # We will assume a product/update webhook for simplicity, which often contains the full variant structure:
    # If your webhook is products/update, you'd iterate through variants and check quantity.
    
    # *** FOR A SIMPLE, RELIABLE WEBHOOK SOLUTION, IT IS BEST TO USE THE VARIANT ID*** # Let's adjust the logic to focus on the **variant_id** and the **inventory_quantity** # directly if possible, or assume the variant_id is known.
    
    # For this example, we'll try to get the variant ID directly from the API using the inventory_item_id, 
    # but the simplest approach is a direct 'inventory_level/update' hook that contains the variant's ID or the item's available stock.
    
    # Let's stick to the simplest version: assume the webhook gives us a variant ID and its current stock.
    # If you use the 'Products/Update' webhook, you'll need to extract this:
    # Example:
    # variants = payload.get('variants', [])
    # for variant in variants:
    #     variant_id = variant['id']
    #     inventory_quantity = variant['inventory_quantity'] 
    
    # --- SIMPLIFIED LOGIC ASSUMING WEBHOOK PROVIDES VARIANT_ID and QUANTITY ---
    # Since the webhook structure is highly dependent on the chosen topic, we will fetch the product details
    # after confirming the inventory_item_id is restocked (quantity > 0).
    
    # NOTE: To get the variant_id from inventory_item_id, you need a graphQL query or REST admin call.
    # This is a complex step. To keep it simple, we will assume you use the 'Products/Update' webhook.

    restocked_variants = []
    
    # Assuming 'Products/Update' webhook payload structure
    product_variants = payload.get('variants', [])
    
    for variant in product_variants:
        variant_id = str(variant.get('id'))
        inventory_quantity = variant.get('inventory_quantity')
        
        if inventory_quantity is not None and inventory_quantity >= 1:
            restocked_variants.append({
                'id': variant_id,
                'quantity': inventory_quantity
            })
            
    if not restocked_variants:
        print("Quantity is below restock threshold or no variants were in the payload.")
        return jsonify({"status": "ok", "message": "No restock condition met."}), 200

    # 3. Process Restocked Variants
    for variant_data in restocked_variants:
        variant_id = variant_data['id']
        subscribers = get_subscribers_for_variant(variant_id)
        
        if not subscribers:
            print(f"No subscribers found for restocked variant {variant_id}.")
            continue

        product_details = get_product_details_by_variant_id(variant_id)

        if not product_details:
            print(f"Could not fetch product details for variant {variant_id}.")
            continue

        # 4. Send Alerts and Delete Subscriptions
        for email in subscribers:
            product_url = f"{STOREFRONT_BASE_URL}/products/{product_details['product_handle']}"
            notification_subject = f"🎉 Back In Stock! {product_details['product_title']}"
            notification_body = (
                f"Great news, {email}! The product you were waiting for "
                f"({product_details['variant_title']}) is officially back in stock!\n\n"
                f"Buy it here: {product_url}\n\n"
                "Note: Your waitlist subscription has been removed."
            )
            
            if send_email(email, notification_subject, notification_body):
                remove_waitlist_entry(email, variant_id)
            
    return jsonify({"status": "ok", "message": "Webhook processed. Alerts sent and subscriptions cleared."}), 200

# --- User/Subscription Endpoints (Keep these) ---
# ... (Copy the /check-subscription, /notify-signup, and / route functions from your original code) ...
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
            {'$set': {'timestamp': datetime.now()}},
            upsert=True
        )
        return True
    except PyMongoError as e:
        print(f"DB Error adding entry: {e}")
        return False

@app.route('/', methods=['GET'])
def home():
    """Simple check for Render health check."""
    return "Shopify Waitlist Service (Webhook-Based) is running.", 200

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


# --- Run Application ---
if __name__ == '__main__':
    # No background thread needed for the webhook method
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)


