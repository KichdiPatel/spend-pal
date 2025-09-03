import logging
from decimal import Decimal
from threading import Timer

from flask import render_template, request
from flask_pydantic import validate
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from twilio.twiml.messaging_response import MessagingResponse

import config
from models.api import (
    ConnectBankRequest,
    CreateLinkTokenRequest,
    CreateLinkTokenResponse,
    PhoneNumberQuery,
    SetBudgetRequest,
    TransactionVerificationRequest,
)
from models.database import db
from server import app, plaid_client
from utils import (
    get_budget_status_text,
    get_pending_transactions_for_verification,
    get_recent_transactions_text,
    get_user_by_phone,
    send_sms,
    update_monthly_totals,
)

# TODO: fix logging
logger = logging.getLogger(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/create_link_token", methods=["POST"])
@validate()
def create_link_token(body: CreateLinkTokenRequest):
    """Create a Plaid Link token for connecting bank accounts.

    Args:
        body: Contains phone number of the user.

    Returns:
        Plaid link token.
    """
    response = plaid_client.link_token_create(
        LinkTokenCreateRequest(
            client_name=config.PLAID_CLIENT_NAME,
            country_codes=[CountryCode.us],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id=body.phone_number),
            products=[Products.transactions],
            webhook=config.PLAID_WEBHOOK_URL,
            redirect_uri=config.PLAID_REDIRECT_URI,
        )
    )

    return CreateLinkTokenResponse(link_token=response["link_token"])


@app.route("/api/connect_bank", methods=["POST"])
@validate()
def connect_bank(body: ConnectBankRequest):
    """Connect bank account using public token.

    Args:
        body: Contains phone number of the user and public token.
    """
    exchange_request = ItemPublicTokenExchangeRequest(public_token=body.public_token)
    exchange_response = plaid_client.item_public_token_exchange(exchange_request)

    user = get_user_by_phone(body.phone_number)
    user.plaid_access_token = exchange_response["access_token"]
    user.plaid_item_id = exchange_response["item_id"]
    db.session.commit()

    send_sms(
        "🎉 Bank account connected! Text 'balance' to see your budget status or 'help' for commands.",
        body.phone_number,
    )


# Budget Management API
@app.route("/api/budget", methods=["GET"])
@validate()
def get_budget(query: PhoneNumberQuery):
    """Get budget categories for a user."""
    user = get_user_by_phone(query.phone_number)
    budget_data = []

    # Direct 1:1 mapping between budget fields and total fields
    budget_mapping = [
        ("Income", user.income_budget, user.income_total),
        ("Transfer In", user.transfer_in_budget, user.transfer_in_total),
        ("Transfer Out", user.transfer_out_budget, user.transfer_out_total),
        ("Loan Payments", user.loan_payments_budget, user.loan_payments_total),
        ("Bank Fees", user.bank_fees_budget, user.bank_fees_total),
        ("Entertainment", user.entertainment_budget, user.entertainment_total),
        ("Food & Drink", user.food_and_drink_budget, user.food_and_drink_total),
        ("Shopping", user.general_merchandise_budget, user.general_merchandise_total),
        ("Home Improvement", user.home_improvement_budget, user.home_improvement_total),
        ("Medical", user.medical_budget, user.medical_total),
        ("Personal Care", user.personal_care_budget, user.personal_care_total),
        ("General Services", user.general_services_budget, user.general_services_total),
        (
            "Government & Non-Profit",
            user.government_and_non_profit_budget,
            user.government_and_non_profit_total,
        ),
        ("Transportation", user.transportation_budget, user.transportation_total),
        ("Travel", user.travel_budget, user.travel_total),
        (
            "Rent & Utilities",
            user.rent_and_utilities_budget,
            user.rent_and_utilities_total,
        ),
    ]

    # Filter to only show categories with budgets set
    active_budgets = [
        (name, budget, total)
        for name, budget, total in budget_mapping
        if budget and budget > 0
    ]

    for name, budget_limit, spent in active_budgets:
        spent = spent or Decimal("0")
        remaining = budget_limit - spent

        budget_data.append(
            {
                "category": name,
                "monthly_limit": float(budget_limit),
                "spent": float(spent),
                "remaining": float(remaining),
            }
        )

    return {"budget": budget_data}


@app.route("/api/budget", methods=["POST"])
@validate()
def set_budget(body: SetBudgetRequest):
    """Set budget limits for a user."""
    user = get_user_by_phone(body.phone_number)

    # Update individual budget fields directly
    budget_limits = body.budget_limits
    user.income_budget = budget_limits.income_budget
    user.transfer_in_budget = budget_limits.transfer_in_budget
    user.transfer_out_budget = budget_limits.transfer_out_budget
    user.loan_payments_budget = budget_limits.loan_payments_budget
    user.bank_fees_budget = budget_limits.bank_fees_budget
    user.entertainment_budget = budget_limits.entertainment_budget
    user.food_and_drink_budget = budget_limits.food_and_drink_budget
    user.general_merchandise_budget = budget_limits.general_merchandise_budget
    user.home_improvement_budget = budget_limits.home_improvement_budget
    user.medical_budget = budget_limits.medical_budget
    user.personal_care_budget = budget_limits.personal_care_budget
    user.general_services_budget = budget_limits.general_services_budget
    user.government_and_non_profit_budget = (
        budget_limits.government_and_non_profit_budget
    )
    user.transportation_budget = budget_limits.transportation_budget
    user.travel_budget = budget_limits.travel_budget
    user.rent_and_utilities_budget = budget_limits.rent_and_utilities_budget

    db.session.commit()


@app.route("/api/transactions/pending", methods=["GET"])
@validate()
def get_pending_transactions(query: PhoneNumberQuery):
    """Get transactions pending verification for a user."""
    user = get_user_by_phone(query.phone_number)
    pending_transactions = get_pending_transactions_for_verification(user)

    transactions_data = []
    for tx in pending_transactions:
        transactions_data.append(
            {
                "id": tx["id"],
                "merchant_name": tx["merchant_name"],
                "amount": float(tx["amount"]),
                "category": tx["category"],
                "date": tx["date"],
                "original_category": tx["original_category"],
            }
        )

    return {"pending_transactions": transactions_data}


@app.route("/api/transactions/verify", methods=["POST"])
@validate()
def verify_transaction(body: TransactionVerificationRequest):
    """Verify a transaction and update monthly totals."""
    user = get_user_by_phone(body.phone_number)

    # Update monthly total for the Plaid category
    update_monthly_totals(
        user, body.category_override or "general_merchandise", body.user_amount
    )

    # Update user's cursor to move past this transaction
    # In a real implementation, you'd want to track which transactions have been verified

    db.session.commit()


@app.route("/api/monthly-totals", methods=["GET"])
@validate()
def get_monthly_totals(query: PhoneNumberQuery):
    """Get current monthly spending totals by category."""
    user = get_user_by_phone(query.phone_number)

    totals = {
        "income": float(user.income_total or 0),
        "transfer_in": float(user.transfer_in_total or 0),
        "transfer_out": float(user.transfer_out_total or 0),
        "loan_payments": float(user.loan_payments_total or 0),
        "bank_fees": float(user.bank_fees_total or 0),
        "entertainment": float(user.entertainment_total or 0),
        "food_and_drink": float(user.food_and_drink_total or 0),
        "general_merchandise": float(user.general_merchandise_total or 0),
        "home_improvement": float(user.home_improvement_total or 0),
        "medical": float(user.medical_total or 0),
        "personal_care": float(user.personal_care_total or 0),
        "general_services": float(user.general_services_total or 0),
        "government_and_non_profit": float(user.government_and_non_profit_total or 0),
        "transportation": float(user.transportation_total or 0),
        "travel": float(user.travel_total or 0),
        "rent_and_utilities": float(user.rent_and_utilities_total or 0),
    }

    return {"monthly_totals": totals}


@app.route("/api/categories", methods=["GET"])
@validate()
def get_available_categories(query: PhoneNumberQuery):
    """Get available categories for transaction categorization."""
    user = get_user_by_phone(query.phone_number)

    # Return Plaid categories that match our budget fields
    plaid_categories = [
        "income",
        "transfer_in",
        "transfer_out",
        "loan_payments",
        "bank_fees",
        "entertainment",
        "food_and_drink",
        "general_merchandise",
        "home_improvement",
        "medical",
        "personal_care",
        "general_services",
        "government_and_non_profit",
        "transportation",
        "travel",
        "rent_and_utilities",
    ]

    return {"categories": plaid_categories}


# SMS Handler
@app.route("/sms", methods=["POST"])
def handle_sms():
    """Handle incoming SMS messages."""
    try:
        # Get SMS data
        from_number = request.form.get("From")
        message_body = request.form.get("Body", "").strip().lower()

        if not from_number:
            return "Invalid request", 400

        # Get or create user
        user = get_user_by_phone(from_number)

        # Handle different commands
        if message_body == "balance" or message_body == "status":
            response_text = get_budget_status_text(user)
        elif message_body == "recent":
            response_text = get_recent_transactions_text(user)
        elif message_body == "pending":
            response_text = get_pending_transactions_text(user)
        elif message_body == "sync":
            # Trigger transaction sync
            from utils import sync_all_users

            sync_all_users()
            response_text = "🔄 Syncing transactions... Check back in a few minutes!"
        elif message_body == "help":
            response_text = (
                "📱 SpendPal SMS Commands:\n\n"
                "💰 balance - Check budget status\n"
                "📊 recent - View monthly spending by category\n"
                "⏳ pending - View transactions needing verification\n"
                "🔄 sync - Update monthly totals\n"
                "❓ help - Show this message"
            )
        else:
            response_text = "❓ Unknown command. Text 'help' for available commands."

        # Send response
        twiml_response = MessagingResponse()
        twiml_response.message(response_text)
        return str(twiml_response)

    except Exception as e:
        logger.error(f"Error handling SMS: {str(e)}")
        twiml_response = MessagingResponse()
        twiml_response.message(
            "❌ Sorry, something went wrong. Please try again later."
        )
        return str(twiml_response)


def run_sync_scheduler():
    """Run the sync scheduler in the background."""
    from utils import sync_all_users

    sync_all_users()
    # Schedule next run in 1 hour
    Timer(3600, run_sync_scheduler).start()


# TODO: create webhook endpoint for plaid to send post requests


# Start sync scheduler when app starts
if __name__ == "__main__":
    run_sync_scheduler()
    app.run(debug=True)
else:
    # For production deployment
    run_sync_scheduler()
