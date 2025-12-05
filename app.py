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
from pywebpush import webpush, WebPushException  # 🔔 Push

# --- Configuration: Reads from Environment Variables ---
try:
    SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL", "raj-dynamic-dreamz.myshopify.com")
    SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY")

    SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "rajpurohit74747@gmail.com")
    EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "vvhj rkau nncu ugdj")  # Gmail App Password
    SHOPIFY_API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2023-10")

    # MongoDB
    MONGODB_URI = os.environ.get(
        "MONGODB_URI",
        "mongodb+srv://rajpurohit74747:raj123@padhaion.qxq1zfs.mongodb.net/?appName=PadhaiOn"
    )

    # 🔔 VAPID Keys for Push Notifications
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "BDwCgw519N3sNXDRO1TvFC-n5FDRK_yKJlmP7oe4Lgqnz5uk9pjHknsxpt4LcTcU7_OGGGWCsHdXdxCUHaVxAFg ")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "s5dJQSGa2lavMc0swU6qKgQwQBDLNe8d5oGx3czzK80")
    VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:rajpurohit7474747@gmail.com")

    # Safely construct base URL for storefront links
    storefront_base_url_env = os.environ.get("STOREFRONT_BASE_URL")
    if storefront_base_url_env:
        STOREFRONT_BASE_URL = storefront_base_url_env.rstrip("/")
    else:
        STOREFRONT_BASE_URL = f"https://{SHOPIFY_STORE_URL}".rstrip("/")

    if not SHOPIFY_API_KEY:
        print("❌ WARNING: SHOPIFY_API_KEY is missing. Stock checker will fail.")
    if not VAPID_PUBLIC_KEY:
        print("❌ WARNING: VAPID keys are missing. Push notifications disabled.")

except Exception as e:
    print(f"FATAL ERROR: Failed to load environment variables. {e}")

app = Flask(__name__)

# --- MongoDB Setup ---
waitlist_collection = None
try:
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client["shopify_waitlist_db"]
    waitlist_collection = db["waitlist_entries"]

    waitlist_collection.create_index([("email", 1), ("variant_id", 1)], unique=True)
    waitlist_collection.create_index([("variant_id", 1)])

    print("✅ Successfully connected to MongoDB and initialized database.")
except (ServerSelectionTimeoutError, PyMongoError, TimeoutError) as e:
    print(f"ERROR: Could not connect to MongoDB. Error: {e}")

# --- CORS ---
CORS(app, resources={r"/*": {"origins": os.environ.get("FRONTEND_ORIGIN", "*")}})

# --- DB Helpers ---

def is_subscribed(email, variant_id):
    if waitlist_collection is None:
        return False
    try:
        return waitlist_collection.find_one(
            {"email": email, "variant_id": str(variant_id)}
        ) is not None
    except PyMongoError as e:
        print(f"DB Error checking subscription: {e}")
        return False


def add_waitlist_entry(email, variant_id, push_subscription=None):
    """
    Adds or updates a waitlist entry, including push subscription.
    """
    if waitlist_collection is None:
        print("DB Not Connected.")
        return False

    try:
        update_fields = {
            "email": email,
            "variant_id": str(variant_id),
            "timestamp": time.time(),
        }

        if (
            push_subscription
            and isinstance(push_subscription, dict)
            and "endpoint" in push_subscription
        ):
            print("✅ Received push_subscription with endpoint:", push_subscription.get("endpoint"))
            update_fields["push_subscription"] = push_subscription
        else:
            print("ℹ️ No valid push_subscription provided; saving email only.")

        waitlist_collection.update_one(
            {"email": email, "variant_id": str(variant_id)},
            {"$set": update_fields},
            upsert=True,
        )
        print("DB upsert waitlist entry:", update_fields)
        return True
    except PyMongoError as e:
        print(f"DB Error adding entry: {e}")
        return False


def get_waitlist_entries():
    if waitlist_collection is None:
        return []
    try:
        return list(waitlist_collection.find())
    except PyMongoError as e:
        print(f"DB Error fetching waitlist: {e}")
        return []


def remove_waitlist_entry(email, variant_id):
    if waitlist_collection is None:
        return False
    try:
        waitlist_collection.delete_one(
            {"email": email, "variant_id": str(variant_id)}
        )
        return True
    except PyMongoError as e:
        print(f"DB Error removing entry: {e}")
        return False

# --- Shopify API Helper ---

def check_shopify_stock(variant_id):
    if not SHOPIFY_STORE_URL or not SHOPIFY_API_KEY:
        print("❌ ERROR: Shopify credentials missing. Cannot check stock.")
        return False

    variant_id_str = str(variant_id)
    match = re.search(r"\d+$", variant_id_str)
    numeric_id = match.group(0) if match else variant_id_str

    if not numeric_id.isdigit():
        print(
            f"❌ ERROR: Could not parse numeric variant ID from {variant_id_str}. Skipping check."
        )
        return False

    url = (
        f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}"
        f"/variants/{numeric_id}.json"
    )
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_API_KEY,
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 404:
            print(
                f"❌ Shopify API Error 404: Variant {numeric_id} not found. Check the ID."
            )
            return False

        response.raise_for_status()

        data = response.json()
        inventory_quantity = data["variant"]["inventory_quantity"]
        print(
            f"✅ Stock check for variant {variant_id} (ID: {numeric_id}): {inventory_quantity} available."
        )

        return inventory_quantity > 0
    except requests.exceptions.HTTPError as http_err:
        print(
            f"❌ Shopify API HTTP Error (Status {response.status_code}) checking variant {variant_id}."
        )
        print("   -> Check SHOPIFY_API_KEY permissions/value.")
        print(f"   -> Details: {http_err}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Shopify API Request Error checking variant {variant_id}. Error: {e}")
        return False

# --- Email Helper ---

def send_email(to_email, subject, body):
    if not all([SMTP_SERVER, EMAIL_ADDRESS, EMAIL_PASSWORD]):
        print("❌ Email configuration missing.")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
            print(f"📧 Email sent successfully to {to_email}")
            return True
    except Exception as e:
        print(
            f"❌ Email sending failed to {to_email}: check Gmail App Password / SMTP."
        )
        print(f"   -> Details: {e}")
        return False

# --- Push Helper ---

def send_push_notification(subscription, payload):
    if not all([VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY]):
        print("❌ VAPID keys missing, cannot send push.")
        return False
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIM_EMAIL},
        )
        print("🔔 Push notification sent successfully.")
        return True
    except WebPushException as e:
        status = e.response.status_code if e.response is not None else "N/A"
        print(f"❌ Push notification failed (Status {status}): {e}")
        if status == 410:
            print("   -> Subscription expired (410), should be removed from DB.")
        return False
    except Exception as e:
        print(f"❌ Push notification failed: {e}")
        return False

# --- Background Stock Checker ---

def stock_checker_task():
    print("Stock checker thread started.")
    CHECK_INTERVAL_SECONDS = 300
    time.sleep(5)

    while True:
        start_time = time.time()
        print(f"--- Starting stock check cycle at {time.ctime(start_time)} ---")

        all_entries = get_waitlist_entries()
        print(f"Checking waitlist for {len(all_entries)} entries.")

        notified_list = []
        variants_to_check = {}

        for entry in all_entries:
            variant_id = entry.get("variant_id")
            if not variant_id:
                continue
            variants_to_check.setdefault(variant_id, []).append(entry)

        for variant_id, entries in variants_to_check.items():
            if not check_shopify_stock(variant_id):
                continue

            notification_subject = "🎉 IN STOCK NOW! Buy Before It Sells Out!"
            notification_url = f"{STOREFRONT_BASE_URL}/cart/{variant_id}:1"

            for entry in entries:
                email = entry.get("email")
                push_subscription = entry.get("push_subscription")

                email_body = (
                    f"Great news, {email}! The product you were waiting for "
                    f"is officially back in stock! Variant ID: {variant_id}.\n\n"
                    f"Don't wait, buy it here: {notification_url}"
                    "\n\nNote: This link adds one item directly to your cart."
                )

                push_payload = {
                    "title": "🔥 Back in Stock!",
                    "body": f"Your variant ({variant_id}) is available now!",
                    "url": notification_url,
                }

                email_ok = False
                push_ok = False

                if email:
                    email_ok = send_email(email, notification_subject, email_body)

                if push_subscription:
                    push_ok = send_push_notification(push_subscription, push_payload)

                if email_ok or push_ok:
                    notified_list.append((email, variant_id))
                    print(
                        f"   -> Notified {email} (Email: {email_ok}, Push: {push_ok})"
                    )
                else:
                    print(
                        f"   -> WARNING: Failed all notifications for {email} (variant {variant_id})."
                    )

        for email, variant_id in set(notified_list):
            if remove_waitlist_entry(email, variant_id):
                print(
                    f"🗑️ Successfully removed {email} for variant {variant_id} from the waitlist."
                )
            else:
                print(
                    f"⚠️ WARNING: Failed to remove {email} for variant {variant_id} from the waitlist."
                )

        end_time = time.time()
        duration = end_time - start_time
        print(
            f"--- Stock check cycle complete. {len(notified_list)} notification attempts made. Duration: {duration:.2f}s ---"
        )

        sleep_duration = CHECK_INTERVAL_SECONDS - duration
        if sleep_duration > 0:
            print(f"😴 Sleeping for {sleep_duration:.0f} seconds.")
            time.sleep(sleep_duration)
        else:
            print(
                f"⚠️ WARNING: Stock check took longer than {CHECK_INTERVAL_SECONDS} seconds. Running next cycle immediately."
            )
            time.sleep(5)

# --- Routes ---

@app.route("/", methods=["GET"])
def home():
    return "Shopify Waitlist Service is running.", 200


@app.route("/check-subscription", methods=["GET"])
def check_subscription():
    email = request.args.get("email")
    variant_id = request.args.get("variant_id")

    if not email or not variant_id:
        return jsonify({"error": "Missing email or variant ID."}), 400

    return jsonify({"subscribed": is_subscribed(email, variant_id)}), 200


@app.route("/vapid-public-key", methods=["GET"])
def vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        return jsonify({"error": "VAPID Public Key not configured on the server."}), 503
    return jsonify({"publicKey": VAPID_PUBLIC_KEY}), 200


@app.route("/notify-signup", methods=["POST"])
def notify_signup():
    try:
        if request.content_type != "application/json":
            return jsonify({"error": "Content-Type must be application/json."}), 415

        data = request.get_json()
        print("📥 /notify-signup REQUEST JSON:", data)

        email = data.get("email")
        variant_id = data.get("variant_id")
        push_subscription = data.get("push_subscription")

        if not email or not variant_id:
            return jsonify({"error": "Missing email or product variant ID."}), 400

        already = is_subscribed(email, variant_id)

        if add_waitlist_entry(email, variant_id, push_subscription):
            if not already:
                initial_subject = "✅ You're on the Waitlist!"
                initial_body = (
                    f"Thanks! We've added your email, {email}, to the notification list "
                    f"for variant {variant_id}. We will send you an alert when it's back in stock."
                )
                send_email(email, initial_subject, initial_body)
                return jsonify(
                    {"message": "Successfully added to the waitlist. Confirmation email sent."}
                ), 200
            else:
                return jsonify({"message": "Subscription updated."}), 200
        else:
            return jsonify({"error": "Failed to save entry to database."}), 500

    except Exception as e:
        print(f"Error processing sign-up request: {e}")
        return jsonify({"error": "Internal server error during processing."}), 500


if __name__ == "__main__":
    if waitlist_collection is not None:
        if not any(t.name == "StockCheckerThread" for t in threading.enumerate()):
            stock_thread = threading.Thread(
                target=stock_checker_task, name="StockCheckerThread"
            )
            stock_thread.daemon = True
            stock_thread.start()
    else:
        print(
            "WARNING: Stock checker not started due to MongoDB connection failure."
        )

    app.run(host="0.0.0.0", port=os.environ.get("PORT", 10000))
