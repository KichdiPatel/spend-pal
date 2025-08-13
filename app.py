import json
import os
from datetime import datetime

import pandas as pd
import plaid
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.transactions_sync_request import TransactionsSyncRequest

load_dotenv()

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "production")
PLAID_WEBHOOK_URL = os.getenv("PLAID_WEBHOOK_URL")
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI")
PLAID_CLIENT_NAME = os.getenv("PLAID_CLIENT_NAME", "YourAppName")
PORT = int(os.getenv("PORT", 8000))
DATABASE_URL = os.getenv("DATABASE_URL")

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

# Initialize Flask application
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)
db = SQLAlchemy(app)


# Database model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(120), unique=True, nullable=False)
    item_id = db.Column(db.String(120), unique=True, nullable=False)


# Initialize the database
with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/create_link_token", methods=["POST"])
def create_link_token():
    request = LinkTokenCreateRequest(
        client_name=PLAID_CLIENT_NAME,
        country_codes=[CountryCode("US")],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id="user"),
        products="transactions",
        webhook=PLAID_WEBHOOK_URL,
        redirect_uri=PLAID_REDIRECT_URI,
    )
    response = client.link_token_create(request)
    return jsonify(response.to_dict())


def exchange_public_token(public_token):
    try:
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response["access_token"]
        item_id = exchange_response["item_id"]

        user = User.query.first()
        if user is None:
            user = User(access_token=access_token, item_id=item_id)
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


# @app.route("/api/get_transactions", methods=["POST"])
# def get_transactions():
#     user = User.query.first()
#     if not user:
#         return jsonify({"error": "User not found"}), 404

#     try:
#         # Calculate the start date of the current month
#         today = dt.date.today()
#         start_date = dt.date(today.year, today.month, 1)

#         # Set the cursor to empty to receive all historical updates
#         cursor = ""
#         transactions = []

#         while True:
#             request = TransactionsSyncRequest(
#                 access_token=user.access_token,
#                 cursor=cursor,
#             )
#             response = client.transactions_sync(request).to_dict()

#             # Add this page of results
#             transactions.extend(response["added"])
#             cursor = response["next_cursor"]

#             if not response["has_more"]:
#                 break

#         # Debugging: Print the transactions to check their structure
#         print("Fetched transactions:")
#         for txn in transactions:
#             print(txn)

#         # Filter transactions to only include those within the current month
#         current_month_transactions = []
#         for txn in transactions:
#             txn_date_str = txn.get("date", "")
#             if isinstance(txn_date_str, str) and txn_date_str:
#                 txn_date = dt.date.fromisoformat(txn_date_str)
#                 if txn_date >= start_date:
#                     current_month_transactions.append(txn)
#             else:
#                 print(f"Skipping transaction with invalid date: {txn}")

#         return jsonify({"transactions": current_month_transactions})
#     except plaid.ApiException as e:
#         print(f"Error fetching transactions: {e}")
#         return jsonify(json.loads(e.body))


@app.route("/api/get_transactions", methods=["POST"])
def get_transactions():
    user = User.query.first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        cursor = ""
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

        df = pd.json_normalize(added)
        df["date"] = pd.to_datetime(df["date"])
        current_year = datetime.now().year
        current_month = datetime.now().month
        filtered_df = df[
            (df["date"].dt.year == current_year)
            & (df["date"].dt.month == current_month)
        ]
        json_str = filtered_df.to_json(orient="records")
        json_obj = json.loads(json_str)
        return jsonify({"latest_transactions": json_obj})
    except plaid.ApiException as e:
        return jsonify(json.loads(e.body))


@app.route("/shutdown", methods=["POST"])
def shutdown():
    shutdown_server()
    return "Server shutting down..."


def shutdown_server():
    func = request.environ.get("werkzeug.server.shutdown")
    if func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
    func()


if __name__ == "__main__":
    app.run(port=PORT, debug=True)
