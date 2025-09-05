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
import logic as logic
from models.api import (
    ConnectBankRequest,
    CreateLinkTokenRequest,
    CreateLinkTokenResponse,
    GetBudgetDataRequest,
    GetBudgetDataResponse,
    UpdateBudgetRequest,
)
from models.database import User
from server import app, plaid_client

# TODO: fix logging
# TODO: add return types throughout whole project

logger = logging.getLogger(__name__)

# TODO: remove db logic from here


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

    logic.connect_bank(body.phone_number, exchange_response)


@app.route("/api/budget", methods=["GET"])
@validate()
def get_budget_data(body: GetBudgetDataRequest):
    """Get budget amounts for a user.

    Args:
        body: Contains phone number of the user.

    Returns:
        Budget amounts and total monthly spend for a user.
    """
    budget_dict, spending_dict = logic.get_budget_data(body.phone_number)

    budgets = GetBudgetDataResponse.Categories(**budget_dict)
    monthly_totals = GetBudgetDataResponse.Categories(**spending_dict)

    return GetBudgetDataResponse(budgets=budgets, monthly_totals=monthly_totals)


@app.route("/api/budget", methods=["PATCH"])
@validate()
def update_budget(body: UpdateBudgetRequest):
    """Update budget limits for a user.

    Args:
        body: Contains phone number of the user and budget limits.
    """
    budget_updates = body.budgets.model_dump(exclude_none=True)

    logic.update_budget(body.phone_number, budget_updates)


# TODO: Fix this endpoint
@app.route("/sms", methods=["POST"])
def handle_sms():
    """Handle incoming SMS messages."""
    from_number = request.form.get("From")
    message_body = request.form.get("Body", "").strip().lower()

    response_text = logic.handle_sms(from_number, message_body)

    twiml_response = MessagingResponse()
    twiml_response.message(response_text)
    return str(twiml_response)


@app.route("/api/plaid/webhook", methods=["POST"])
# TODO: fix the get User to include plaid_item_id and use here
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
            logic.sync_single_user(user)
            logger.info(f"Triggered sync for user {user.phone_number} via webhook")

    if webhook_code == "ERROR":
        item_id = webhook_data.get("item_id")
        user = User.query.filter_by(plaid_item_id=item_id).first()
        logger.exception(f"Received ERROR webhook for item_id: {item_id}")


def run_sync_scheduler():
    """Run the sync scheduler in the background."""

    logic.sync_all_users()
    Timer(3600, run_sync_scheduler).start()


# Start sync scheduler when app starts
if __name__ == "__main__":
    run_sync_scheduler()
    app.run(debug=True)
else:
    # For production deployment
    run_sync_scheduler()
