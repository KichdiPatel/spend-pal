from datetime import datetime, timedelta

from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import (
    TransactionsGetRequestOptions,
)
from plaid.model.transactions_sync_request import TransactionsSyncRequest

import config
from models.database import User
from server import db, plaid_client, twilio_client


def _get_user(
    phone_number: str | None = None, plaid_item_id: str | None = None
) -> User:
    """Get user by phone number or plaid item id.

    Args:
        phone_number: Phone number of the user.
        plaid_item_id: Plaid item id of the user.

    Returns:
        User object.
    """
    if phone_number:
        return User.query.filter_by(phone_number=phone_number).first()
    elif plaid_item_id:
        return User.query.filter_by(plaid_item_id=plaid_item_id).first()
    else:
        raise ValueError("Either phone number or plaid item id must be provided")


def _send_sms(message: str, to_number: str = None):
    """Send SMS message via Twilio."""
    to_number = to_number or config.USER_PHONE_NUMBER
    message = twilio_client.messages.create(
        body=message, from_=config.TWILIO_PHONE_NUMBER, to=to_number
    )


def connect_bank(phone_number: str, exchange_response: dict) -> None:
    """Connect bank account using public token.

    Args:
        phone_number: Phone number of the user.
        exchange_response: Exchange response from Plaid.
    """
    user = _get_user(phone_number=phone_number)
    user.plaid_access_token = exchange_response["access_token"]
    user.plaid_item_id = exchange_response["item_id"]
    db.session.commit()

    _send_sms(
        "🎉 Bank account connected! Text 'balance' to see your budget status or 'help' for commands.",
        phone_number,
    )


def get_budget_data(phone_number: str) -> tuple[dict, dict]:
    """Get budget data for a user.

    Args:
        phone_number: Phone number of the user.

    Returns:
        Tuple of budget and spending data.
    """
    user = _get_user(phone_number=phone_number)

    budget_dict = {
        k: v
        for k, v in user.budgets.__dict__.items()
        if not k.startswith("_")
        and k not in ["user_id", "month_year", "created_at", "updated_at"]
    }

    spending_dict = {
        k: v
        for k, v in user.monthly_spending.__dict__.items()
        if not k.startswith("_") and k not in ["user_id", "created_at", "updated_at"]
    }

    return budget_dict, spending_dict


def update_budget(phone_number: str, budget_updates: dict) -> None:
    """Update budget for a user.

    Args:
        phone_number: Phone number of the user.
        budget_updates: Budget updates.
    """
    user = _get_user(phone_number=phone_number)
    for field_name, value in budget_updates.items():
        setattr(user.budgets, field_name, value)
    db.session.commit()


def handle_sms(phone_number: str, message_body: str) -> str:
    """Handle SMS messages from a user.

    Args:
        phone_number: Phone number of the user.
        message_body: Message body from the user.
    """

    def _valid_float(message_body: str) -> bool:
        """Check if the message body is a valid float.

        Args:
            message_body: Message body from the user.

        Returns:
            True if the message body is a valid float, False otherwise.
        """
        try:
            float(message_body)
            return True
        except ValueError:
            return False

    user = _get_user(phone_number=phone_number)
    message_body = message_body.strip("$")

    if user.currently_reconciling:
        if message_body == "status":
            return "Finishing reconciling before you can see your budget status!"

        elif message_body == "correct":
            curr_amount = getattr(user.monthly_spending, user.reconcile_category)
            amount = curr_amount + user.reconcile_amount

            setattr(user.monthly_spending, user.reconcile_category, amount)
            user.currently_reconciling = False
            user.reconcile_category = None
            user.reconcile_amount = None
            user.reconcile_transaction_id = None

            # Check for next transaction in queue
            sync_single_user(user)

            return "Transaction confirmed!"

        elif _valid_float(message_body):
            curr_amount = getattr(user.monthly_spending, user.reconcile_category)
            amount = curr_amount + float(message_body)

            setattr(user.monthly_spending, user.reconcile_category, amount)
            user.currently_reconciling = False
            user.reconcile_category = None
            user.reconcile_amount = None
            user.reconcile_transaction_id = None

            # Check for next transaction in queue
            sync_single_user(user)

            return "Transaction confirmed!"

        else:
            return "Please respond with 'correct' or a valid amount"

    else:
        if message_body == "status":
            spending_dict = {
                k: v
                for k, v in user.monthly_spending.__dict__.items()
                if not k.startswith("_")
                and k not in ["user_id", "created_at", "updated_at"]
            }

            categories_with_spending = []
            for field_name, spending_val in spending_dict.items():
                if spending_val > 0:
                    budget_val = getattr(user.budgets, field_name)
                    display_name = field_name.replace("_", " ").title()
                    categories_with_spending.append(
                        (display_name, budget_val, spending_val)
                    )

            if not categories_with_spending:
                return "💰 No spending this month yet!"

            # TODO: update this format
            status_lines = ["💰 Budget Status (Categories with Spending):"]
            total_spent = 0
            total_budget = 0

            for name, budget_limit, spent in categories_with_spending:
                spent = spent or 0
                budget_limit = budget_limit or 0

                if budget_limit > 0:
                    percentage = (spent / budget_limit) * 100
                    emoji = "🟢" if spent <= budget_limit else "🔴"
                    status_lines.append(
                        f"{emoji} {name}: ${spent:.2f}/${budget_limit:.2f} ({percentage:.1f}%)"
                    )
                else:
                    # No budget set for this category
                    status_lines.append(f"⚪ {name}: ${spent:.2f} (no budget set)")

                total_spent += spent
                total_budget += budget_limit

            if total_budget > 0:
                overall_percentage = (total_spent / total_budget) * 100
                status_lines.append(
                    f"\n💳 Total: ${total_spent:.2f}/${total_budget:.2f} ({overall_percentage:.1f}%)"
                )
            else:
                status_lines.append(
                    f"\n💳 Total Spent: ${total_spent:.2f} (no budgets set)"
                )

            return "\n".join(status_lines)
        else:
            response_text = "Text 'balance' to see your budget status"

    return response_text


# TODO: fix this function
def sync_single_user(user: User):
    """Check for new Plaid transactions and start reconciliation if needed."""

    # Only proceed if user is not currently reconciling
    if user.currently_reconciling:
        return

    # If there are transactions in the queue, process the next one
    if user.transaction_queue:
        transaction_id = user.transaction_queue.pop(0)

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        request = TransactionsGetRequest(
            access_token=user.plaid_access_token,
            start_date=start_date,
            end_date=end_date,
            options=TransactionsGetRequestOptions(transaction_ids=[transaction_id]),
        )

        response = plaid_client.transactions_get(request).to_dict()

        transactions = response.get("transactions", [])

        if not transactions:
            db.session.commit()
            sync_single_user(user)
            return

        tx = transactions[0]

        user.currently_reconciling = True
        user.reconcile_category = (
            tx["personal_finance_category"]["primary"].lower()
            if tx["personal_finance_category"]["primary"]
            else "general_merchandise"
        )
        user.reconcile_amount = abs(float(tx["amount"]))
        user.reconcile_transaction_id = transaction_id

        db.session.commit()

        merchant_name = tx["merchant_name"] or tx["name"]
        message = f"""New Transaction:
                    Location: {merchant_name}
                    Category: {user.reconcile_category.replace("_", " ").title()}
                    Amount: ${user.reconcile_amount:.2f}

                    Is this correct or did you pay a different amount? (Ex. Split the bill). Type 'Correct' or the value you owe.
                    """

        _send_sms(message, user.phone_number)

    else:
        cursor = user.plaid_cursor or ""
        request_data = TransactionsSyncRequest(
            access_token=user.plaid_access_token,
            cursor=cursor,
        )

        response = plaid_client.transactions_sync(request_data).to_dict()
        new_transactions = response.get("added", [])

        if new_transactions:
            transaction_ids = [tx["transaction_id"] for tx in new_transactions]
            user.transaction_queue.extend(transaction_ids)
            user.plaid_cursor = response.get("next_cursor", cursor)
            db.session.commit()

            sync_single_user(user)
            return

        if response.get("next_cursor"):
            user.plaid_cursor = response["next_cursor"]
            db.session.commit()


def sync_all_users():
    """Sync all users."""
    users = User.query.all()
    for user in users:
        sync_single_user(user)


# TODO: plaid webhook logic

# TODO: sync scheduler logic
