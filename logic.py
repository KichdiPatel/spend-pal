from datetime import datetime, timedelta

from loguru import logger
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest

import config
from models.database import Budget, MonthlySpending, User
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


def _send_sms(message: str, to_number: str = None) -> None:
    """Send SMS message via Twilio."""
    to_number = to_number or config.USER_PHONE_NUMBER
    message = twilio_client.messages.create(
        body=message, from_=config.TWILIO_PHONE_NUMBER, to=to_number
    )
    logger.info(f"SMS sent to {to_number}")


def _get_tx_attributes(user: User, transaction_id: str) -> dict:
    """Get transaction attributes from Plaid using transaction ID.

    Args:
        user: User object with Plaid access token.
        transaction_id: Plaid transaction ID.

    Returns:
        Dictionary with transaction attributes (amount, category, date, merchant, etc.)
        Returns None if transaction not found.
    """
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    request = TransactionsGetRequest(
        access_token=user.plaid_access_token,
        start_date=start_date,
        end_date=end_date,
    )

    response = plaid_client.transactions_get(request).to_dict()

    transactions = response.get("transactions", [])

    # Find the specific transaction by ID
    tx = None
    for transaction in transactions:
        if transaction["transaction_id"] == transaction_id:
            tx = transaction
            break

    if not tx:
        return None

    return {
        "transaction_id": tx["transaction_id"],
        "amount": abs(float(tx["amount"])),
        "category": (
            tx["personal_finance_category"]["primary"].lower()
            if tx["personal_finance_category"]["primary"]
            else "general_merchandise"
        ),
        "date": tx["date"],
        "merchant_name": tx["merchant_name"] or tx["name"],
        "account_id": tx["account_id"],
        "pending": tx["pending"],
        "subcategory": (
            tx["personal_finance_category"]["detailed"]
            if tx["personal_finance_category"]["detailed"]
            else None
        ),
        "original_amount": float(tx["amount"]),
    }


def _clear_monthly_spending(user: User) -> None:
    """Clear all spending values in MonthlySpending table for a given user.

    Args:
        user: User object to clear spending for.
    """
    monthly_spending = user.monthly_spending

    spending_fields = [
        col.name
        for col in monthly_spending.__table__.columns
        if col.name not in ["user_id", "created_at", "updated_at"]
    ]

    for field in spending_fields:
        setattr(monthly_spending, field, None)

    db.session.commit()


def connect_bank(phone_number: str, exchange_response: dict) -> None:
    """Connect bank account using public token.

    Args:
        phone_number: Phone number of the user.
        exchange_response: Exchange response from Plaid.
    """
    user = _get_user(phone_number=phone_number)

    if user is None:
        user = User(
            phone_number=phone_number,
            plaid_access_token="",
            plaid_item_id="",
            plaid_cursor="",
        )
        db.session.add(user)
        db.session.flush()

        budget = Budget(user_id=user.id)
        monthly_spending = MonthlySpending(user_id=user.id)
        db.session.add(budget)
        db.session.add(monthly_spending)
    else:
        budget = user.budgets
        monthly_spending = user.monthly_spending

        for field in budget.__table__.columns:
            if field.name != "user_id":
                setattr(budget, field.name, None)

        for field in monthly_spending.__table__.columns:
            if field.name != "user_id":
                setattr(monthly_spending, field.name, None)

    user.plaid_access_token = exchange_response["access_token"]
    user.plaid_item_id = exchange_response["item_id"]
    user.plaid_cursor = ""
    db.session.commit()

    _send_sms(
        "🎉 Bank account connected! Text 'balance' to see your budget status.",
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
        k: v if v is not None else 0.0
        for k, v in user.budgets.__dict__.items()
        if not k.startswith("_")
        and k not in ["user_id", "month_year", "created_at", "updated_at"]
    }

    spending_dict = {
        k: v if v is not None else 0.0
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
    """Handle SMS messages from a user. If the user is reconciling a transaction,
    the message body is the amount they owe or 'correct'. If the user is not reconciling a transaction,
    the message body can only be 'status'.

    Args:
        phone_number: Phone number of the user.
        message_body: Message body from the user.

    Returns:
        Response text.
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

    if user.current_reconciling_tx_id:
        tx_attributes = _get_tx_attributes(user, user.current_reconciling_tx_id)

        if message_body == "status":
            return "Finishing reconciling before you can see your budget status!"

        elif message_body == "correct":
            amount = tx_attributes["amount"]

        elif _valid_float(message_body):
            amount = float(message_body)

        else:
            return "Please respond with 'correct' or a valid amount"

        tx_date = datetime.strptime(tx_attributes["date"], "%Y-%m-%d").date()
        tx_month = tx_date.replace(day=1)

        if user.current_month is None or user.current_month != tx_month:
            _clear_monthly_spending(user)
            user.current_month = tx_month

        curr_amount = getattr(user.monthly_spending, tx_attributes["category"]) + amount
        setattr(user.monthly_spending, tx_attributes["category"], curr_amount)
        user.current_reconciling_tx_id = None
        db.session.commit()

        sync_single_user(user)
        return "Transaction confirmed!"

    else:
        if message_body == "balance":
            spending_dict = {
                k: v if v is not None else 0.0
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
            status_lines = ["💰 Budget Status (Categories with Spending):\n"]
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


def plaid_webhook(item_id: str) -> None:
    """Handle Plaid webhook.

    Args:
        item_id: Plaid item id.
    """
    user = _get_user(plaid_item_id=item_id)

    if user:
        sync_single_user(user)


def sync_single_user(user: User) -> None:
    """Check for new Plaid transactions and start reconciliation if needed.
    If the user is currently reconciling a transaction, this function does nothing.
    If the user has a transaction in the queue, the function will start the reconciliation process.
    Otherwise, the function will sync the user's transactions using plaid's cursor-based sync.

    Args:
        user: User object.
    """
    logger.info(f"Syncing user {user.phone_number}")
    logger.info(
        f"Transaction queue LENGTH STARTING SYNC: {len(user.transaction_queue)}"
    )

    if user.current_reconciling_tx_id:
        return

    if user.transaction_queue:
        logger.info(f"Transaction queue FOUND: {len(user.transaction_queue)}")
        transaction_id = user.transaction_queue.pop(0)

        tx_attrs = _get_tx_attributes(user, transaction_id)

        if not tx_attrs:
            db.session.commit()
            db.session.refresh(user)
            sync_single_user(user)
            return

        user.currently_reconciling = True
        user.reconcile_category = tx_attrs["category"]
        user.reconcile_amount = tx_attrs["amount"]
        user.reconcile_transaction_id = transaction_id

        db.session.commit()

        message = f"""New Transaction:
                    Location: {tx_attrs["merchant_name"]}
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

        try:
            response = plaid_client.transactions_sync(request_data).to_dict()
            # logger.info(f"Plaid sync response: {response}")
            new_transactions = response.get("added", [])
            logger.info(f"New transactions: {len(new_transactions)}")
            if new_transactions:
                transaction_ids = [tx["transaction_id"] for tx in new_transactions]
                # logger.info(f"Transaction IDs: {transaction_ids}")
                user.transaction_queue.extend(transaction_ids)
                logger.info(f"Transaction queue: {len(user.transaction_queue)}")
                user.plaid_cursor = response.get("next_cursor", cursor)
                db.session.commit()

                db.session.refresh(user)

                check_user = _get_user(phone_number=user.phone_number)
                logger.info(
                    f"Transaction queue LENGTH AFTER SYNC: {len(check_user.transaction_queue)}"
                )
                sync_single_user(user)
                return

            elif response.get("next_cursor"):
                user.plaid_cursor = response["next_cursor"]
                db.session.commit()

        except Exception as e:
            error_msg = str(e)
            if "INVALID_ACCESS_TOKEN" in error_msg and "environment" in error_msg:
                logger.error(
                    f"Environment mismatch for user {user.phone_number}: Access token is for different Plaid environment"
                )
            else:
                logger.warning(f"Plaid sync error for user {user.phone_number}: {e}")

            user.plaid_cursor = ""
            _clear_monthly_spending(user)
            db.session.commit()


def sync_all_users():
    """Sync all users."""
    users = User.query.all()
    for user in users:
        sync_single_user(user)
