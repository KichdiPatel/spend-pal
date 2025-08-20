import logging
from datetime import datetime
from decimal import Decimal
from threading import Timer

from flask import jsonify, render_template, request
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from twilio.twiml.messaging_response import MessagingResponse

import config
from models import BudgetCategory, Transaction, db
from server import app, plaid_client
from utils import (
    get_budget_status_text,
    get_pending_transactions_text,
    get_user_by_phone,
    notify_new_transaction,
    process_transaction_response,
    sync_all_users,
    sync_transactions_for_user,
)

# Set up logging
logger = logging.getLogger(__name__)


# API Routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/create_link_token", methods=["POST"])
def create_link_token():
    """Create a Plaid Link token for connecting bank accounts."""
    data = request.get_json()
    phone_number = data.get("phone_number")

    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    request_data = LinkTokenCreateRequest(
        client_name=config.PLAID_CLIENT_NAME,
        country_codes=[CountryCode.us],
        language="en",
        user=LinkTokenCreateRequestUser(client_user_id=phone_number),
        products=[Products.transactions],
        webhook=config.PLAID_WEBHOOK_URL,
        redirect_uri=config.PLAID_REDIRECT_URI,
    )
    response = plaid_client.link_token_create(request_data)
    return jsonify(response.to_dict())


@app.route("/api/connect_bank", methods=["POST"])
def connect_bank():
    """Connect bank account using public token."""
    data = request.get_json()
    public_token = data.get("public_token")
    phone_number = data.get("phone_number")

    if not public_token or not phone_number:
        return jsonify({"error": "public_token and phone_number are required"}), 400

    # Exchange public token for access token
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    exchange_response = plaid_client.item_public_token_exchange(exchange_request)

    # Get or create user
    user = get_user_by_phone(phone_number)
    user.plaid_access_token = exchange_response["access_token"]
    user.plaid_item_id = exchange_response["item_id"]
    db.session.commit()

    # Send welcome SMS
    from utils import send_sms

    send_sms(
        "🎉 Bank account connected! Text 'balance' to see your budget status or 'help' for commands."
    )

    return jsonify({"status": "success"})


# Budget Management API
@app.route("/api/budget", methods=["GET"])
def get_budget():
    """Get budget categories for a user."""
    phone_number = request.args.get("phone_number")
    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    user = get_user_by_phone(phone_number)
    budget_data = []

    for category in user.budget_categories:
        # Calculate spent amount for current month
        current_month = datetime.now().replace(day=1).date()
        spent = db.session.query(db.func.sum(Transaction.user_amount)).filter(
            Transaction.user_id == user.id,
            Transaction.category == category.name,
            Transaction.date >= current_month,
            ~Transaction.is_pending_review,
            Transaction.user_amount.isnot(None),
        ).scalar() or Decimal("0")

        budget_data.append(
            {
                "category": category.name,
                "monthly_limit": float(category.monthly_limit),
                "spent": float(spent),
                "remaining": float(category.monthly_limit - spent),
            }
        )

    return jsonify({"budget": budget_data})


@app.route("/api/budget", methods=["POST"])
def set_budget():
    """Set budget categories for a user."""
    data = request.get_json()
    phone_number = data.get("phone_number")
    categories = data.get("categories", [])

    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    user = get_user_by_phone(phone_number)

    # Clear existing budget categories
    BudgetCategory.query.filter_by(user_id=user.id).delete()

    # Add new categories
    for cat_data in categories:
        category = BudgetCategory(
            user_id=user.id,
            name=cat_data["name"],
            monthly_limit=Decimal(str(cat_data["monthly_limit"])),
        )
        db.session.add(category)

    db.session.commit()
    return jsonify({"status": "success"})


@app.route("/api/transactions/pending", methods=["GET"])
def get_pending_transactions():
    """Get transactions pending review for a user."""
    phone_number = request.args.get("phone_number")
    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    user = get_user_by_phone(phone_number)
    pending_transactions = (
        Transaction.query.filter_by(user_id=user.id, is_pending_review=True)
        .order_by(Transaction.date.desc())
        .all()
    )

    transactions_data = []
    for tx in pending_transactions:
        transactions_data.append(
            {
                "id": tx.id,
                "merchant_name": tx.merchant_name,
                "amount": float(tx.amount),
                "category": tx.category,
                "date": tx.date.isoformat(),
                "needs_split": tx.needs_split,
            }
        )

    return jsonify({"pending_transactions": transactions_data})


@app.route("/api/categories", methods=["GET"])
def get_available_categories():
    """Get available categories for transaction categorization."""
    phone_number = request.args.get("phone_number")
    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    user = get_user_by_phone(phone_number)

    # User's budget categories (preferred)
    user_categories = [
        {"name": cat.name, "type": "budget"} for cat in user.budget_categories
    ]

    # Common Plaid categories as fallback options
    common_categories = [
        {"name": "Food and Drink", "type": "standard"},
        {"name": "Restaurants", "type": "standard"},
        {"name": "Groceries", "type": "standard"},
        {"name": "Shopping", "type": "standard"},
        {"name": "Transportation", "type": "standard"},
        {"name": "Gas Stations", "type": "standard"},
        {"name": "Entertainment", "type": "standard"},
        {"name": "Healthcare Services", "type": "standard"},
        {"name": "Utilities", "type": "standard"},
        {"name": "Travel", "type": "standard"},
        {"name": "Other", "type": "standard"},
    ]

    return jsonify(
        {"user_categories": user_categories, "standard_categories": common_categories}
    )


@app.route("/api/transactions/<int:transaction_id>/review", methods=["POST"])
def review_transaction(transaction_id):
    """Review and approve a transaction with optional category override."""
    data = request.get_json()
    user_amount = data.get("user_amount")
    needs_split = data.get("needs_split", False)
    new_category = data.get("category")  # Allow category override

    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        return jsonify({"error": "Transaction not found"}), 404

    transaction.user_amount = (
        Decimal(str(user_amount)) if user_amount else transaction.amount
    )
    transaction.needs_split = needs_split

    # Allow category override
    if new_category and new_category != transaction.category:
        transaction.category = new_category

    transaction.is_pending_review = False
    transaction.reviewed_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"status": "success"})


# SMS Handling
@app.route("/sms", methods=["POST"])
def handle_sms():
    """Handle incoming SMS messages."""
    from_number = request.values.get("From", "")
    message_body = request.values.get("Body", "").strip()

    resp = MessagingResponse()

    try:
        user = get_user_by_phone(from_number)
        message_lower = message_body.lower()

        # Check if user has pending transaction responses first
        has_pending_response = (
            Transaction.query.filter_by(
                user_id=user.id, awaiting_sms_response=True
            ).first()
            is not None
        )

        if has_pending_response and message_lower not in [
            "help",
            "balance",
            "pending",
            "sync",
        ]:
            # Process as transaction response
            response_text = process_transaction_response(user, message_body)
            resp.message(response_text)

        elif message_lower == "help":
            help_text = """📱 SpendPal Commands:
• balance - See your budget status
• pending - View transactions needing review
• sync - Check for new transactions
• help - Show this message

Reply to transaction notifications with:
• 'full' - You owe the full amount
• '25' - You owe $25
• '25,Food' - You owe $25, categorize as Food"""
            resp.message(help_text)

        elif message_lower == "balance":
            budget_text = get_budget_status_text(user)
            resp.message(budget_text)

        elif message_lower == "pending":
            pending_text = get_pending_transactions_text(user)
            resp.message(pending_text)

        elif message_lower == "sync":
            new_transactions = sync_transactions_for_user(user)
            if new_transactions:
                resp.message(
                    f"🔄 Found {len(new_transactions)} new transactions! Check your messages for details."
                )
                # Send notifications for each new transaction
                for tx in new_transactions:
                    notify_new_transaction(user, tx)
            else:
                resp.message("✅ No new transactions found.")

        else:
            resp.message("❓ Unknown command. Text 'help' to see available commands.")

    return str(resp)


# Background Tasks
def run_sync_scheduler():
    """Run the transaction sync scheduler."""
    logger.info("Starting transaction sync scheduler...")
    with app.app_context():
        sync_all_users()
    Timer(3600, run_sync_scheduler).start()  # Run every hour


# Health check
@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify(
        {"status": "healthy", "timestamp": datetime.now().isoformat(), "version": "2.0"}
    )


# Initialize scheduler
run_sync_scheduler()

if __name__ == "__main__":
    app.run(port=config.PORT, debug=True)
