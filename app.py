import os
import requests
import json
import hmac
import hashlib
from flask import Flask, render_template, jsonify, request, abort
from flask_mail import Mail, Message
from pymongo import MongoClient
from datetime import datetime

# --- CONFIGURATION (YOUR ACTUAL VALUES) ---
SHOPIFY_STORE_NAME = "raj-dynamic-dreamz"
SHOPIFY_API_VERSION = "2024-10"
SHOPIFY_ACCESS_TOKEN = "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" 

# IMPORTANT: You MUST set this secret in your Shopify Webhook setup!
SHOPIFY_WEBHOOK_SECRET = "3c3b8d61c508e9b950ca22a8e91cadc819491c5785dc35780af05002f5ca5e56" # <-- CHANGE THIS TO A SECURE RANDOM STRING

MONGO_URI = "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?retryWrites=true&w=majority&appName=PadhaiOn"
MONGO_DB_NAME = "shopify_waitlist_db"
MONGO_COLLECTION_NAME = "waitlist_entries"

# Email Configuration
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = 'rajpurohit74747@gmail.com'
MAIL_PASSWORD = 'vvhj rkau nncu ugdj'
MAIL_DEFAULT_SENDER = 'Alert System <rajpurohit7474747@gmail.com>'

# --- FLASK APP & EXTENSION SETUP ---
app = Flask(__name__)
app.config.update(
    MAIL_SERVER=MAIL_SERVER,
    MAIL_PORT=MAIL_PORT,
    MAIL_USE_TLS=MAIL_USE_TLS,
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_DEFAULT_SENDER=MAIL_DEFAULT_SENDER
)
mail = Mail(app)

# MongoDB Setup
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    subscribers_collection = db[MONGO_COLLECTION_NAME]
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"MongoDB connection failed: {e}")
    client = None
    subscribers_collection = None

# --- WEBHOOK SECURITY FUNCTION ---

def verify_webhook_hmac(data, hmac_header):
    """Verifies that the incoming request is truly from Shopify."""
    if not SHOPIFY_WEBHOOK_SECRET:
        print("Webhook secret not configured!")
        return False
        
    encoded_secret = SHOPIFY_WEBHOOK_SECRET.encode('utf-8')
    digest = hmac.new(encoded_secret, data, hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(digest, hmac_header)

# --- WEBHOOK ENDPOINT: INSTANT ALERT LOGIC ---

@app.route('/webhook/inventory-update', methods=['POST'])
def inventory_webhook():
    """Receives data instantly from Shopify when inventory changes."""
    
    # 1. Get raw data and HMAC header for verification
    data = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256')

    # 2. SECURITY CHECK: Verify the request origin
    if not verify_webhook_hmac(data, hmac_header):
        print("SECURITY ALERT: HMAC verification failed for incoming webhook.")
        abort(401) # Unauthorized

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        print("Failed to parse JSON payload.")
        abort(400) # Bad Request

    # 3. Extract necessary data from the payload (this webhook gives location-specific inventory)
    variant_id = str(payload.get('variant_id'))
    inventory_quantity = payload.get('available') # 'available' refers to inventory at this location
    
    print(f"Webhook received for Variant ID: {variant_id}. New Quantity: {inventory_quantity}")

    # 4. Check Restock Condition
    RESTOCK_THRESHOLD = 1
    if inventory_quantity < RESTOCK_THRESHOLD:
        print("Quantity is below restock threshold. Skipping alerts.")
        return jsonify({"status": "ok", "message": "Not enough stock to alert."}), 200

    # 5. Get subscribers for this variant
    subscribers = get_subscribers_for_variant(variant_id)
    
    if not subscribers:
        print(f"No subscribers found for restocked variant {variant_id}.")
        return jsonify({"status": "ok", "message": "No subscribers found."}), 200

    # 6. Fetch Product Details (We need title, handle, etc., which aren't in the inventory webhook)
    product_details = get_product_details_by_variant_id(variant_id)

    if not product_details:
        print(f"Could not fetch product details for variant {variant_id}.")
        return jsonify({"status": "ok", "message": "Product details missing."}), 200

    # 7. Send Alerts and Delete Subscriptions
    total_alerts_sent = 0
    for email in subscribers:
        if send_restock_email(
            email, 
            product_details['product_title'], 
            product_details['variant_title'], 
            product_details['product_handle']
        ):
            total_alerts_sent += 1
            # CRUCIAL: REMOVE SUBSCRIPTION
            subscribers_collection.delete_one({
                "email": email, 
                "variant_id": str(variant_id)
            })
            
    return jsonify({
        "status": "ok", 
        "message": f"Alerts processed for variant {variant_id}. Sent {total_alerts_sent} emails."
    }), 200


# --- NEW HELPER FUNCTION TO GET PRODUCT DETAILS ---

def get_product_details_by_variant_id(variant_id):
    """
    Fetches the necessary product/variant details (like title and handle) 
    for the email template, as the inventory webhook only provides IDs and quantity.
    """
    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/variants/{variant_id}.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        variant_data = data.get('variant', {})
        
        # Need to fetch the parent product data too to get the handle/title
        product_id = variant_data.get('product_id')
        if not product_id: return None

        product_url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/products/{product_id}.json"
        product_response = requests.get(product_url, headers=headers, timeout=5)
        product_response.raise_for_status()
        product_data = product_response.json().get('product', {})

        return {
            'product_title': product_data.get('title', 'Restocked Item'),
            'product_handle': product_data.get('handle', ''),
            'variant_title': variant_data.get('title', 'Default'),
            'inventory': variant_data.get('inventory_quantity', 0)
        }

    except requests.exceptions.RequestException as e:
        print(f"Shopify API (details fetch) failed: {e}")
        return None


# --- REMAINING FUNCTIONS (Minimal changes) ---

def fetch_shopify_product_data():
    """(Kept for the dashboard /api/products route)"""
    # Fetching code remains the same as previous steps...
    # NOTE: Since this is now only for the dashboard display, 
    # we can remove the inventory check from here if needed, but keeping 
    # the GraphQL query as-is is simpler for the dashboard.
    url = f"https://{SHOPIFY_STORE_NAME}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }

    query = """
    query GetProductVariants {
      products(first: 50) {
        edges {
          node {
            title
            handle 
            variants(first: 50) {
              edges {
                node {
                  id
                  title
                  sku
                  inventoryQuantity
                }
              }
            }
          }
        }
      }
    }
    """
    payload = {"query": query}

    try:
        # ... (rest of the GraphQL execution logic) ...
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        products_data = []
        
        for product_edge in data.get('data', {}).get('products', {}).get('edges', []):
            product_node = product_edge.get('node', {})
            variant_edges = product_node.get('variants', {}).get('edges', [])
            
            for variant_edge in variant_edges:
                variant_node = variant_edge.get('node', {})
                variant_gid = variant_node.get('id')
                variant_id = variant_gid.split('/')[-1] if variant_gid else None

                products_data.append({
                    'product_title': product_node.get('title'),
                    'product_handle': product_node.get('handle'), 
                    'variant_id': variant_id,
                    'variant_title': variant_node.get('title'),
                    'sku': variant_node.get('sku', 'N/A'),
                    'inventory': variant_node.get('inventoryQuantity', 0)
                })
        
        return products_data
        
    except requests.exceptions.RequestException as e:
        print(f"Shopify API Request failed: {e}")
        return []
    except Exception as e:
        print(f"Error processing Shopify data: {e}")
        return []

def get_subscribers_for_variant(variant_id):
    """Retrieves all unique subscriber emails for a specific variant ID."""
    if subscribers_collection is None:
        return []
    try:
        subscriptions = subscribers_collection.find(
            {"variant_id": str(variant_id)},
            {"email": 1, "_id": 0} 
        )
        return list(set(doc['email'] for doc in subscriptions))
    except Exception as e:
        print(f"Error fetching subscribers from MongoDB: {e}")
        return []

def send_restock_email(recipient_email, product_title, variant_title, product_handle):
    """Sends a restock alert email."""
    try:
        # (Email sending logic remains the same)
        msg = Message(
            subject=f"In Stock Alert: {product_title} ({variant_title})",
            recipients=[recipient_email],
            html=render_template(
                'email_template.html', 
                product_title=product_title, 
                variant_title=variant_title,
                product_handle=product_handle, 
                SHOPIFY_STORE_NAME=SHOPIFY_STORE_NAME
            )
        )
        mail.send(msg)
        print(f"Email sent successfully to {recipient_email}")
        return True
    except Exception as e:
        print(f"Failed to send email to {recipient_email}: {e}")
        return False

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/products', methods=['GET'])
def get_products():
    products = fetch_shopify_product_data()
    if not products:
        return jsonify({"error": "Could not retrieve products from Shopify."}), 500
    return jsonify(products)


# NOTE: You can now remove /api/send-alert and /api/setup-db as the webhook handles the restock logic.
# I will keep the setup-db for testing convenience, but remove the manual send-alert.

@app.route('/api/setup-db', methods=['POST'])
def setup_db():
    if subscribers_collection is None:
        return jsonify({"message": "MongoDB not connected."}), 500

    # Ensure this variant ID exists and you can change its stock for testing!
    variant_to_subscribe = "54378128310563" 
    test_email = "test@example.com"
    
    existing_subscription = subscribers_collection.find_one({
        "email": test_email,
        "variant_id": str(variant_to_subscribe)
    })

    if existing_subscription:
        return jsonify({
            "message": f"Test user {test_email} is already subscribed to variant {variant_to_subscribe}."
        })
    else:
        subscribers_collection.insert_one({
            "email": test_email,
            "variant_id": str(variant_to_subscribe),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        })
        return jsonify({
            "message": f"Test subscriber {test_email} created and subscribed to variant {variant_to_subscribe}. Use this variant ID for testing the webhook."
        })

if __name__ == '__main__':
    # We no longer need use_reloader=False as we removed APScheduler
    app.run(debug=True)
