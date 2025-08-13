import json
import logging
import math
import os
from datetime import datetime, timezone
from threading import Timer

import pandas as pd
import plaid
import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode  # Import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from psycopg2 import OperationalError
from sqlalchemy import Boolean
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

# Set up logging
logging.basicConfig(level=logging.INFO)

# Load environment variables from the .env file
load_dotenv()

# Load environment variables
# plaid variables
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "production")
PLAID_PRODUCTS = os.getenv("PLAID_PRODUCTS", "transactions").split(",")
PLAID_COUNTRY_CODES = os.getenv("PLAID_COUNTRY_CODES", "US").split(",")
PLAID_WEBHOOK_URL = os.getenv("PLAID_WEBHOOK_URL")
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI")
PLAID_CLIENT_NAME = os.getenv("PLAID_CLIENT_NAME", "YourAppName")
PORT = 5000

# database variable
DATABASE_URL = os.getenv("DATABASE_URL")
print(DATABASE_URL)

# twilio variables
ACCOUNT_SID = os.getenv("ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
USER_PHONE_NUM = os.getenv("USER_PHONE_NUM")
TWILIO_NUM = os.getenv("TWILIO_NUM")

# Verify the DATABASE_URL
if not DATABASE_URL:
    logging.error("DATABASE_URL is not set or is empty.")
    exit(1)

# Set up the Plaid environment
host = (
    plaid.Environment.Sandbox
    if PLAID_ENV == "sandbox"
    else plaid.Environment.Production
)

# Configure the Plaid client
configuration = plaid.Configuration(
    host=host,
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET,
        "plaidVersion": "2020-09-14",
    },
)

api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

products = [Products(product) for product in PLAID_PRODUCTS]

# Initialize Flask application
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)

# Test database connection
try:
    connection = psycopg2.connect(DATABASE_URL)
    cursor = connection.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    logging.info(f"Connected to PostgreSQL, version: {db_version}")
except OperationalError as e:
    logging.error(f"Error connecting to the database: {e}")
    exit(1)
finally:
    if connection:
        cursor.close()
        connection.close()

# Initialize SQLAlchemy
try:
    db = SQLAlchemy(app)
    logging.info("Database initialized successfully.")
except Exception as e:
    logging.error(f"Error initializing the database: {e}")
    logging.error(f"Exception details: {e.__class__.__name__}: {e}")
    exit(1)


# Database model
class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(120), unique=True, nullable=False)
    item_id = db.Column(db.String(120), unique=True, nullable=False)
    cursor = db.Column(db.String(120), nullable=True)
    currentMonth = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    needsReconcile = db.Column(Boolean, nullable=False, default=False)
    currentlyReconciling = db.Column(Boolean, nullable=False, default=False)
    currentTx = db.Column(db.String(255), nullable=True)


class NewTx(db.Model):
    __tablename__ = "newTxs"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, nullable=False)
    date = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class ApprovedTxs(db.Model):
    __tablename__ = "approvedTxs"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, nullable=False)
    date = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Initialize the database
with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/create_link_token", methods=["POST"])
def create_link_token():
    try:
        request = LinkTokenCreateRequest(
            client_name=PLAID_CLIENT_NAME,
            country_codes=[CountryCode(code) for code in PLAID_COUNTRY_CODES],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id="user"),
            products=products,
            webhook=PLAID_WEBHOOK_URL,
            redirect_uri=PLAID_REDIRECT_URI,
        )
        response = client.link_token_create(request)
        return jsonify(response.to_dict())
    except plaid.ApiException as e:
        print(json.loads(e.body))  # Debugging statement
        return jsonify(json.loads(e.body))


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print(f"Webhook received: {json.dumps(data, indent=2)}")

    if "public_token" in data:
        public_token = data["public_token"]
        exchange_public_token(public_token)

    return jsonify(status="success"), 200


def exchange_public_token(public_token):
    try:
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response["access_token"]
        item_id = exchange_response["item_id"]

        # Save the access token and item ID in the database
        user = User.query.first()
        if user is None:
            user = User(
                access_token=access_token,
                item_id=item_id,
                currentMonth=datetime.now(),
                needsReconcile=False,
                currentlyReconciling=False,
            )
        else:
            user.access_token = access_token
            user.item_id = item_id
        db.session.add(user)
        db.session.commit()

        print(f"Access token: {access_token}")
        print(f"Item ID: {item_id}")
    except plaid.ApiException as e:
        print(json.loads(e.body))


@app.route("/api/set_access_token", methods=["POST"])
def set_access_token():
    public_token = request.json["public_token"]
    try:
        exchange_public_token(public_token)
        return jsonify({"status": "success"})
    except plaid.ApiException as e:
        return jsonify(json.loads(e.body))


@app.route("/api/get_transactions", methods=["POST"])
def get_transactions():
    user = User.query.first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        if not user.cursor:
            cursor = ""
        else:
            cursor = user.cursor
        print(cursor)
        added = []
        modified = []
        removed = []
        has_more = True

        while has_more:
            request = TransactionsSyncRequest(
                access_token=user.access_token,
                cursor=cursor,
            )
            response = client.transactions_sync(request).to_dict()
            added.extend(response["added"])
            modified.extend(response["modified"])
            removed.extend(response["removed"])
            has_more = response["has_more"]
            cursor = response["next_cursor"]

        df = pd.DataFrame(added)

        print(df["category_id"].value_counts())
        # Get current date
        today = datetime.today().date()

        # Get the first and last date of the current month
        first_day_of_month = today.replace(day=1)
        last_day_of_month = (first_day_of_month + pd.offsets.MonthEnd(0)).date()

        # Filter and sort the DataFrame
        current_month_df = df[
            (df["date"] >= first_day_of_month) & (df["date"] <= last_day_of_month)
        ].sort_values(by="date")

        current_month_json = json.loads(current_month_df.to_json(orient="records"))
        return jsonify({"latest_transactions": current_month_json})
    except plaid.ApiException as e:
        return jsonify(json.loads(e.body))


@app.route("/api/new_transactions", methods=["POST"])
def get_new_transactions():
    user = User.query.first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    try:
        if not user.cursor:
            cursor = ""
        else:
            cursor = user.cursor

        added = []
        modified = []
        removed = []
        has_more = True

        while has_more:
            request = TransactionsSyncRequest(
                access_token=user.access_token,
                cursor=cursor,
            )
            response = client.transactions_sync(request).to_dict()
            added.extend(response["added"])
            modified.extend(response["modified"])
            removed.extend(response["removed"])
            has_more = response["has_more"]
            cursor = response["next_cursor"]
        if len(added) > 0:
            df = pd.DataFrame(added)
            # Get current date
            today = datetime.today().date()

            # Get the first and last date of the current month
            first_day_of_month = today.replace(day=1)
            last_day_of_month = (first_day_of_month + pd.offsets.MonthEnd(0)).date()

            # Filter and sort the DataFrame
            current_month_df = df[
                (df["date"] >= first_day_of_month) & (df["date"] <= last_day_of_month)
            ].sort_values(by="date")

            current_month_json = json.loads(current_month_df.to_json(orient="records"))

            for tx in current_month_json:
                tx_date = pd.to_datetime(tx["date"], unit="ms")

                new_tx = NewTx(
                    name=tx["name"],
                    amount=tx["amount"],
                    category=tx["category"][0],
                    category_id=int(tx["category_id"]),
                    date=tx_date,
                )

                db.session.add(new_tx)
                db.session.commit()

            user.cursor = cursor
            db.session.add(user)
            db.session.commit()

            return jsonify({"latest_transactions": current_month_json})
        else:
            return jsonify({"latest_transactions": []})
    except plaid.ApiException as e:
        return jsonify(json.loads(e.body))


def hourlyCheck():
    with app.app_context():
        get_new_transactions()
        current_date = datetime.now(timezone.utc)
        current_month = current_date.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # Query the user
        user = User.query.first()
        if user:
            user_current_month = user.currentMonth.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
            )
            # Check if the currentMonth field is different from the current month
            if user_current_month != current_month:
                print("months not equal. Clearing db...")
                # Clear the NewTx database
                NewTx.query.delete()
                ApprovedTxs.query.delete()
                # Update user's currentMonth to the current month
                user.currentMonth = current_date
                db.session.add(user)
            # Check the number of observations in the NewTx database
            new_tx_count = NewTx.query.count()
            if new_tx_count > 0:
                user.needsReconcile = True
                sendText(
                    "You have txs that need to be reconciled. Text ‘reconcile’ to begin. Reply with the transaction name and new details (amount or 'same', new category or 'same') if you want to adjust, or just reply 'approve' to approve this transaction."
                )
            else:
                user.needsReconcile = False

            db.session.add(user)
            db.session.commit()


def run_hourly_check():
    print("Starting hourly check...")

    hourlyCheck()
    Timer(3600, run_hourly_check).start()


def sendText(msg):
    client = Client(ACCOUNT_SID, TWILIO_AUTH)
    client.messages.create(to=USER_PHONE_NUM, from_=TWILIO_NUM, body=msg)


def getBudget():
    BUDGET = json.loads(os.getenv("BUDGET"))
    budget_df = pd.DataFrame(list(BUDGET.items()), columns=["category", "budget"])

    approved_transactions = ApprovedTxs.query.all()

    # Convert the query result to a list of dictionaries
    data = [
        {
            "name": tx.name,
            "amount": tx.amount,
            "category": tx.category,
            "category_id": tx.category_id,
            "date": tx.date,
        }
        for tx in approved_transactions
    ]

    # Convert the list of dictionaries to a pandas DataFrame
    df = pd.DataFrame(data)
    df = df.groupby("category")["amount"].sum().reset_index()
    df = df.sort_values(by="amount", ascending=False)

    merged_df = pd.merge(df, budget_df, on="category", how="left")
    merged_df["budget"] = merged_df["budget"].fillna(0)

    message_lines = []
    for index, row in merged_df.iterrows():
        line = f"{row['category']}: {math.floor(row['amount'])}/{math.floor(row['budget'])}"
        message_lines.append(line)
    message = "\n".join(message_lines)

    return message


# Modify the reconcile function to handle state
def reconcile():
    transactions = NewTx.query.all()
    user = User.query.first()

    if not transactions or not user:
        return jsonify({"status": "No transactions or user not found"}), 404

    user.currentlyReconciling = True
    db.session.add(user)
    db.session.commit()

    # Start reconciling the first transaction
    if transactions:
        tx = transactions[0]
        user.currentTx = tx.name
        db.session.add(user)
        db.session.commit()
        send_transaction_message(tx)

    return jsonify({"status": "Reconciliation started"}), 200


# Function to send transaction message
def send_transaction_message(tx):
    message = (
        f"Transaction: {tx.name}\n"
        f"Amount: {tx.amount}\n"
        f"Category: {tx.category}\n"
        f"Date: {tx.date.strftime('%Y-%m-%d')}\n\n"
    )
    sendText(message)


# Update the sms_reply route to handle responses
@app.route("/sms", methods=["GET", "POST"])
def sms_reply():
    user = User.query.first()
    incoming_msg = request.values.get("Body", "").strip()
    resp = MessagingResponse()

    if user.currentlyReconciling:
        tx = NewTx.query.filter_by(name=user.currentTx).first()
        if incoming_msg.lower() == "approve":
            approved_tx = ApprovedTxs(
                name=tx.name,
                amount=tx.amount,
                category=tx.category,
                category_id=tx.category_id,
                date=tx.date,
            )
            db.session.add(approved_tx)
            db.session.commit()
            NewTx.query.filter_by(name=tx.name).delete()
            db.session.commit()
        else:
            parts = incoming_msg.split(",")
            if len(parts) == 2:
                tx_amount, tx_category = parts
                if tx_amount.lower() != "same":
                    tx.amount = float(tx_amount.strip())
                if tx_category.lower() != "same":
                    tx.category = tx_category.strip()

                db.session.add(tx)
                db.session.commit()

                approved_tx = ApprovedTxs(
                    name=tx.name,
                    amount=tx.amount,
                    category=tx.category,
                    category_id=tx.category_id,
                    date=tx.date,
                )
                db.session.add(approved_tx)
                db.session.commit()
                NewTx.query.filter_by(name=tx.name).delete()
                db.session.commit()

        # Check if there are more transactions to reconcile
        next_tx = NewTx.query.first()
        if next_tx:
            user.currentTx = next_tx.name
            db.session.add(user)
            db.session.commit()
            send_transaction_message(next_tx)
        else:
            user.currentlyReconciling = False
            user.needsReconcile = False
            user.currentTx = None
            db.session.add(user)
            db.session.commit()
            resp.message("Reconciliation completed.")

    else:
        if incoming_msg.lower() == "budget" and user.needsReconcile == False:
            budget = getBudget()
            resp.message(budget)

        elif incoming_msg.lower() == "reconcile" and user.needsReconcile == True:
            reconcile()

        elif incoming_msg.lower() != "reconcile" and user.needsReconcile == True:
            resp.message(
                "Please type 'reconcile' to begin reconciling. No other actions can take place until you reconcile your transactions."
            )

        elif incoming_msg.lower() != "budget" and user.needsReconcile == False:
            resp.message(
                "Currently the only available command is 'budget' to retrieve your current budget scenario"
            )

    return str(resp)


def initialize():
    run_hourly_check()


# Ensure this runs regardless of how the script is started
initialize()

if __name__ == "__main__":
    app.run(port=PORT, debug=True)
