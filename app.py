from threading import Timer

from flask import render_template, request
from flask_pydantic import validate
from loguru import logger
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
from server import app, plaid_client

# TODO: add return response types Pydantic


@app.route("/")
def index():
    """Render the index page."""
    return render_template("index.html")


# TODO: remove this later
@app.route("/favicon.ico")
def favicon():
    """Handle favicon requests to prevent 404 errors."""
    return "", 204


@app.route("/api/create_link_token", methods=["POST"])
@validate()
def create_link_token(body: CreateLinkTokenRequest) -> CreateLinkTokenResponse:
    """Create a Plaid Link token for connecting bank accounts.

    Args:
        body: Contains phone number of the user.

    Returns:
        Plaid link token.
    """
    response = plaid_client.link_token_create(
        LinkTokenCreateRequest(
            client_name=config.PLAID_CLIENT_NAME,
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id=body.phone_number),
            products=[Products("transactions")],
            webhook=config.PLAID_WEBHOOK_URL,
            redirect_uri=config.PLAID_REDIRECT_URI,
        )
    )

    return CreateLinkTokenResponse(link_token=response.link_token)


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
    return "Bank account connected successfully", 200


@app.route("/api/budget", methods=["GET"])
@validate(query=GetBudgetDataRequest)
def get_budget_data(query: GetBudgetDataRequest) -> GetBudgetDataResponse:
    """Get budget amounts for a user.

    Args:
        query: Contains phone number of the user.

    Returns:
        Budget amounts and total monthly spend for a user.
    """
    budget_dict, spending_dict = logic.get_budget_data(query.phone_number)

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
    return "Budget updated successfully", 200


# TODO: update to accept message errors to webhook from twilio
@app.route("/sms", methods=["POST"])
def handle_sms() -> str:
    """Handle incoming SMS messages.

    Returns:
        TwiML response.
    """
    from_number = request.form.get("From")
    message_body = request.form.get("Body", "").strip().lower()

    response_text = logic.handle_sms(from_number, message_body)

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
        logic.plaid_webhook(webhook_data.get("item_id"))

    elif webhook_code == "ERROR":
        item_id = webhook_data.get("item_id")
        logger.exception(f"Received ERROR webhook for item_id: {item_id}")

    return "OK", 200


def run_sync_scheduler():
    """Run the sync scheduler in the background."""
    with app.app_context():
        logic.sync_all_users()
    Timer(3600, run_sync_scheduler).start()


# TODO: delete user endpoint

if __name__ == "__main__":
    with app.app_context():
        run_sync_scheduler()
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
