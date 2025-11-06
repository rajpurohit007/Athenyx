import os
import requests
from flask import Flask, render_template, jsonify, request
from flask_mail import Mail, Message
from pymongo import MongoClient
from datetime import datetime
# ADDED: APScheduler for scheduling the inventory check
from flask_apscheduler import APScheduler 

# --- CONFIGURATION (YOUR ACTUAL VALUES) ---
SHOPIFY_STORE_NAME = "raj-dynamic-dreamz"
SHOPIFY_API_VERSION = "2024-10"
SHOPIFY_ACCESS_TOKEN = "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" 

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

# APScheduler Configuration
class Config:
    SCHEDULER_API_ENABLED = True
    # Run the check every 5 minutes (adjust as needed)
    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': True,
        'max_instances': 1
    }
    SCHEDULER_EXECUTORS = {
        'default': {'type': 'threadpool', 'max_workers': 20}
    }
    SCHEDULER_JOBSTORES = {
        'default': {'type': 'memory'}
    }

app.config.from_object(Config())
scheduler = APScheduler()

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

# --- APSCHEDULER JOB: THE AUTOMATION CORE ---

def get_restock_check_threshold():
    """Sets a minimum quantity for restock (e.g., 1 or 5)"""
    return 1 # Alert when stock is 1 or more

# ADDED: This function runs automatically on a schedule
def check_inventory_and_send_alerts():
    """
    1. Fetches current Shopify inventory.
    2. Compares against subscribed variant IDs.
    3. Sends alerts for restocked items and removes subscriptions.
    """
    if subscribers_collection is None:
        print("ALERT JOB FAILED: MongoDB not connected.")
        return

    print(f"--- Running Automated Inventory Check at {datetime.now()} ---")
    
    # 1. Fetch ALL current product data from Shopify
    products_data = fetch_shopify_product_data()
    
    # 2. Identify variants that are currently in stock (or above threshold)
    restocked_variants = {
        p['variant_id']: p for p in products_data 
        if p['inventory'] >= get_restock_check_threshold()
    }
    
    if not restocked_variants:
        print("No restocked variants found above threshold. Skipping alerts.")
        return
        
    # 3. Process alerts for restocked variants
    total_alerts_sent = 0
    total_subscriptions_removed = 0
    
    for variant_id, product in restocked_variants.items():
        # Get all subscribers for this specific variant
        subscribers = get_subscribers_for_variant(variant_id)
        
        if not subscribers:
            continue
            
        print(f"Found {len(subscribers)} subscribers for restocked variant ID {variant_id} ({product['product_title']}).")
        
        # Send alerts
        for email in subscribers:
            if send_restock_email(email, product['product_title'], product['variant_title'], product['product_handle']):
                total_alerts_sent += 1
                
                # CRUCIAL STEP: REMOVE THE SUBSCRIPTION AFTER SENDING THE ALERT
                # We assume a successful email means the user is notified.
                subscribers_collection.delete_one({
                    "email": email, 
                    "variant_id": str(variant_id)
                })
                total_subscriptions_removed += 1
            
    print(f"--- Inventory Check Complete. Sent {total_alerts_sent} alerts and removed {total_subscriptions_removed} subscriptions. ---")


# --- APScheduler Setup and Start ---
if __name__ == '__main__':
    # Initialize the scheduler
    scheduler.init_app(app)
    # Add the automated job: Run every 5 minutes
    scheduler.add_job(
        id='inventory_check', 
        func=check_inventory_and_send_alerts, 
        trigger='interval', 
        minutes=5,
        misfire_grace_time=300 # Allow job to run if missed by 5 minutes
    )
    scheduler.start()
    
    # When running locally, set debug=True. In production, use a WSGI server.
    app.run(debug=True, use_reloader=False) # use_reloader=False is necessary with APScheduler

# --- REMAINING FUNCTIONS (No changes needed, but included for completeness) ---

def fetch_shopify_product_data():
    """Fetches Product Variants, including the product handle for URL creation."""
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
    """Sends a restock alert email, passing the product handle for the dynamic link."""
    try:
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

# Removed the /api/send-alert route as it is now redundant, 
# but I'll leave it in for now so your dashboard buttons still work manually.
@app.route('/api/send-alert', methods=['POST'])
def send_alert():
    data = request.json
    variant_id = data.get('variant_id')
    product_title = data.get('product_title')
    variant_title = data.get('variant_title')
    product_handle = data.get('product_handle')

    if not all([variant_id, product_title, variant_title, product_handle]):
        return jsonify({"message": "Missing required variant data (including product_handle)."}), 400

    subscribers = get_subscribers_for_variant(variant_id)
    
    if not subscribers:
        return jsonify({"message": f"Alert sent, but no subscribers found in MongoDB for variant ID {variant_id}."}), 200

    success_count = 0
    fail_count = 0

    for email in subscribers:
        if send_restock_email(email, product_title, variant_title, product_handle):
            success_count += 1
            # OPTIONAL: You could remove the subscription here too after a manual send.
        else:
            fail_count += 1
            
    return jsonify({
        "message": f"Manual Alert process completed for variant ID {variant_id}.",
        "subscribers_found": len(subscribers),
        "emails_sent_successfully": success_count,
        "emails_failed": fail_count
    }), 200

@app.route('/api/products', methods=['GET'])
def get_products():
    products = fetch_shopify_product_data()
    if not products:
        return jsonify({"error": "Could not retrieve products from Shopify."}), 500
    return jsonify(products)


@app.route('/api/setup-db', methods=['POST'])
def setup_db():
    """
    (FOR DEMO ONLY) Adds a fake subscriber to the database 
    to simulate a subscription, matching your uploaded schema.
    """
    if subscribers_collection is None:
        return jsonify({"message": "MongoDB not connected."}), 500

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
            "message": f"Test subscriber {test_email} created and subscribed to variant {variant_to_subscribe}. Use this variant ID for testing the 'Send Alert' button, or wait for the automated job."
        })
