import logging
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
    GetBudgetDataRequest,
    GetBudgetDataResponse,
    UpdateBudgetRequest,
)
from models.database import User, db
from server import app, plaid_client
from utils import (
    get_budget_status_text,
    get_user_by_phone,
    send_sms,
    sync_all_users,
    sync_user_transactions,
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


@app.route("/api/budget", methods=["GET"])
@validate()
def get_budget_data(body: GetBudgetDataRequest):
    """Get budget amounts for a user.

    Args:
        body: Contains phone number of the user.

    Returns:
        Budget amounts and total monthly spend for a user.
    """
    user = get_user_by_phone(body.phone_number)

    budgets = GetBudgetDataResponse.Categories(
        income=user.income_budget,
        transfer_in=user.transfer_in_budget,
        transfer_out=user.transfer_out_budget,
        loan_payments=user.loan_payments_budget,
        bank_fees=user.bank_fees_budget,
        entertainment=user.entertainment_budget,
        food_and_drink=user.food_and_drink_budget,
        general_merchandise=user.general_merchandise_budget,
        home_improvement=user.home_improvement_budget,
        medical=user.medical_budget,
        personal_care=user.personal_care_budget,
        general_services=user.general_services_budget,
        government_and_non_profit=user.government_and_non_profit_budget,
        transportation=user.transportation_budget,
        travel=user.travel_budget,
        rent_and_utilities=user.rent_and_utilities_budget,
    )

    monthly_totals = GetBudgetDataResponse.Categories(
        income=user.income_total,
        transfer_in=user.transfer_in_total,
        transfer_out=user.transfer_out_total,
        loan_payments=user.loan_payments_total,
        bank_fees=user.bank_fees_total,
        entertainment=user.entertainment_total,
        food_and_drink=user.food_and_drink_total,
        general_merchandise=user.general_merchandise_total,
        home_improvement=user.home_improvement_total,
        medical=user.medical_total,
        personal_care=user.personal_care_total,
        general_services=user.general_services_total,
        government_and_non_profit=user.government_and_non_profit_total,
        transportation=user.transportation_total,
        travel=user.travel_total,
        rent_and_utilities=user.rent_and_utilities_total,
    )

    return GetBudgetDataResponse(budgets=budgets, monthly_totals=monthly_totals)


@app.route("/api/budget", methods=["PATCH"])
@validate()
def update_budget(body: UpdateBudgetRequest):
    """Update budget limits for a user.

    Args:
        body: Contains phone number of the user and budget limits.
    """
    user = get_user_by_phone(body.phone_number)

    budget_updates = body.budgets.model_dump(exclude_none=True)

    for field_name, value in budget_updates.items():
        db_field_name = f"{field_name}_budget"
        if hasattr(user, db_field_name):
            setattr(user, db_field_name, value)

    db.session.commit()


# TODO: Fix this endpoint
@app.route("/sms", methods=["POST"])
def handle_sms():
    """Handle incoming SMS messages."""
    from_number = request.form.get("From")
    message_body = request.form.get("Body", "").strip().lower()

    user = get_user_by_phone(from_number)

    if message_body == "status":
        response_text = get_budget_status_text(user)
    else:
        response_text = "📱 SpendPal: Text 'balance' to see your budget status"

    # Send response
    twiml_response = MessagingResponse()
    twiml_response.message(response_text)
    return str(twiml_response)


@app.route("/api/plaid/webhook", methods=["POST"])
def plaid_webhook():
    """Handle webhooks from Plaid for real-time transaction updates."""
    webhook_data = request.get_json()

    webhook_type = webhook_data.get("webhook_type")
    webhook_code = webhook_data.get("webhook_code")

    if (
        webhook_type == "TRANSACTIONS"
        and webhook_code == "TRANSACTIONS_SYNC_UPDATES_AVAILABLE"
    ):
        item_id = webhook_data.get("item_id")

        user = User.query.filter_by(plaid_item_id=item_id).first()
        if user:
            sync_user_transactions(user)
            logger.info(f"Triggered sync for user {user.phone_number} via webhook")

    if webhook_code == "ERROR":
        item_id = webhook_data.get("item_id")
        user = User.query.filter_by(plaid_item_id=item_id).first()
        logger.exception(f"Received ERROR webhook for item_id: {item_id}")


def run_sync_scheduler():
    """Run the sync scheduler in the background."""

    sync_all_users()
    Timer(3600, run_sync_scheduler).start()


# Start sync scheduler when app starts
if __name__ == "__main__":
    run_sync_scheduler()
    app.run(debug=True)
else:
    # For production deployment
    run_sync_scheduler()
