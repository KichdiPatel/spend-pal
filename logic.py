from datetime import datetime
from textwrap import dedent

from loguru import logger
from plaid.model.transactions_sync_request import TransactionsSyncRequest

import config
from models.database import Budget, Transactions, User
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


def _clear_old_transactions(user: User) -> None:
    """Clear all transactions from Transactions table that have a date before the current month.

    Args:
        user: User object to clear transactions for.
    """
    current_month = datetime.now().date().replace(day=1)

    Transactions.query.filter(
        Transactions.user_id == user.id, Transactions.date < current_month
    ).delete()

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
        db.session.add(budget)
    else:
        budget = user.budgets

        for field in budget.__table__.columns:
            if field.name != "user_id":
                setattr(budget, field.name, None)

    user.plaid_access_token = exchange_response["access_token"]
    user.plaid_item_id = exchange_response["item_id"]
    user.plaid_cursor = ""
    db.session.commit()

    _send_sms(
        "🎉 Bank account connected! Text 'balance' to see your budget status.",
        phone_number,
    )


def delete_user(phone_number: str) -> None:
    """Delete a user.

    Args:
        phone_number: Phone number of the user.
    """
    user = _get_user(phone_number=phone_number)
    db.session.delete(user)
    db.session.commit()


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

    current_month = datetime.now().date().replace(day=1)
    if current_month.month == 12:
        next_month = current_month.replace(year=current_month.year + 1, month=1)
    else:
        next_month = current_month.replace(month=current_month.month + 1)

    current_transactions = Transactions.query.filter(
        Transactions.user_id == user.id,
        Transactions.date >= current_month,
        Transactions.date < next_month,
        Transactions.reconciled,
    ).all()

    spending_dict = {}
    for tx in current_transactions:
        category = tx.plaid_category.lower()
        amount = float(tx.amount) if tx.amount else 0.0
        spending_dict[category] = spending_dict.get(category, 0) + amount

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


def plaid_webhook(item_id: str) -> None:
    """Handle Plaid webhook.

    Args:
        item_id: Plaid item id.
    """
    user = _get_user(plaid_item_id=item_id)

    if user:
        sync_single_user(user.phone_number)


def handle_sms(phone_number: str, message_body: str) -> str | None:
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
        tx = Transactions.query.filter(
            Transactions.user_id == user.id,
            Transactions.tx_id == user.current_reconciling_tx_id,
        ).first()

        if message_body == "status":
            return "Finishing reconciling before you can see your budget status!"

        elif message_body == "correct":
            pass

        elif _valid_float(message_body):
            tx.amount = float(message_body)

        else:
            return "Please respond with 'correct' or a valid amount"

        _clear_old_transactions(user)

        user.current_reconciling_tx_id = None
        tx.reconciled = True
        db.session.commit()

        # _send_sms("Transaction confirmed!", user.phone_number)  # Commented out to avoid twilio exepenses
        sync_single_user(user.phone_number)
        return None

    else:
        if message_body == "balance":
            current_month = datetime.now().date().replace(day=1)
            if current_month.month == 12:
                next_month = current_month.replace(year=current_month.year + 1, month=1)
            else:
                next_month = current_month.replace(month=current_month.month + 1)

            current_transactions = Transactions.query.filter(
                Transactions.user_id == user.id,
                Transactions.date >= current_month,
                Transactions.date < next_month,
                Transactions.reconciled,
            ).all()

            budget_data = user.budgets.__dict__
            full_spending_data = []
            for tx in current_transactions:
                category = tx.plaid_category
                amount = float(tx.amount) if tx.amount else 0.0
                budget_val = budget_data.get(category, 0) or 0
                display_name = category.replace("_", " ").title()
                full_spending_data.append((display_name, budget_val, amount))

            if not full_spending_data:
                return "💰 No spending this month yet!"

            status_lines = ["💰 Budget Status:\n"]
            total_spent = 0
            total_budget = 0

            for name, budget_limit, spent in full_spending_data:
                percentage = (spent / budget_limit) * 100 if budget_limit > 0 else 0
                emoji = "🟢" if spent <= budget_limit else "🔴"
                status_lines.append(
                    f"{emoji} {name}: ${spent:.2f}/${budget_limit:.2f} ({percentage:.1f}%)"
                )

                total_spent += spent
                total_budget += budget_limit

            overall_percentage = (
                (total_spent / total_budget) * 100 if total_budget > 0 else 0
            )
            status_lines.append(
                f"\n💳 Total: ${total_spent:.2f}/${total_budget:.2f} ({overall_percentage:.1f}%)"
            )

            return "\n".join(status_lines)
        else:
            response_text = "Text 'balance' to see your budget status"

    return response_text


def sync_single_user(phone_number: str) -> None:
    """Sync single user."""
    logger.info(f"Syncing user {phone_number}")
    user = _get_user(phone_number=phone_number)

    if not user or user.current_reconciling_tx_id:
        return

    transactions = Transactions.query.filter(
        Transactions.user_id == user.id, Transactions.reconciled.is_(False)
    ).all()

    if not transactions:
        user.current_reconciling_tx_id = None
        db.session.commit()

        cursor = user.plaid_cursor or ""
        request_data = TransactionsSyncRequest(
            access_token=user.plaid_access_token,
            cursor=cursor,
        )

        try:
            response = plaid_client.transactions_sync(request_data).to_dict()
            new_transactions = response.get("added", [])

            if new_transactions:
                for tx in new_transactions:
                    transaction = Transactions(
                        user_id=user.id,
                        tx_id=tx["transaction_id"],
                        amount=tx["amount"],
                        plaid_category=tx["personal_finance_category"]["primary"],
                        date=tx["date"],
                        merchant_name=tx["merchant_name"] or "Unknown Merchant",
                    )
                    db.session.add(transaction)

                user.plaid_cursor = response.get("next_cursor", cursor)
                db.session.commit()

                _clear_old_transactions(user)

                sync_single_user(user.phone_number)
                return

            else:
                user.plaid_cursor = response.get("next_cursor", cursor)
                db.session.commit()

        except Exception:
            logger.exception(f"Error syncing user {phone_number}")
            user.plaid_cursor = ""

            Transactions.query.filter(Transactions.user_id == user.id).delete()
            db.session.commit()
            db.session.commit()

    else:
        tx = transactions[0]
        user.current_reconciling_tx_id = tx.tx_id
        db.session.commit()

        message = dedent(f"""
            New Transaction:
            Location: {tx.merchant_name}
            Date: {tx.date}
            Category: {tx.plaid_category.replace("_", " ").title()}
            Amount: ${tx.amount:.2f}

            Is this correct or did you pay a different amount? (Ex. Split the bill). Type 'Correct' or the value you owe.
        """).strip()

        _send_sms(message, user.phone_number)


def sync_all_users():
    """Sync all users."""
    users = User.query.all()
    for user in users:
        sync_single_user(user.phone_number)
