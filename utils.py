import logging
from datetime import datetime
from decimal import Decimal

import config
from models import Transaction, User, db
from server import twilio_client

logger = logging.getLogger(__name__)


def send_sms(message: str, to_number: str = None):
    """Send SMS message via Twilio."""
    try:
        to_number = to_number or config.USER_PHONE_NUMBER
        message = twilio_client.messages.create(
            body=message, from_=config.TWILIO_PHONE_NUMBER, to=to_number
        )
        logger.info(f"SMS sent to {to_number}: {message.sid}")
        return True
    except Exception as e:
        logger.error(f"Failed to send SMS: {str(e)}")
        return False


def get_user_by_phone(phone_number: str) -> User:
    """Get or create user by phone number."""
    user = User.query.filter_by(phone_number=phone_number).first()
    if not user:
        user = User(phone_number=phone_number)
        db.session.add(user)
        db.session.commit()
        logger.info(f"Created new user with phone: {phone_number}")
    return user


def map_plaid_category_to_budget(user: User, plaid_category: str) -> str:
    """Map Plaid category to user's budget category, or return closest match."""
    if not plaid_category:
        return "Other"

    # Get user's budget category names (lowercase for matching)
    user_categories = {cat.name.lower(): cat.name for cat in user.budget_categories}
    plaid_lower = plaid_category.lower()

    # Direct match
    if plaid_lower in user_categories:
        return user_categories[plaid_lower]

    # Smart mapping from common Plaid categories to budget categories
    category_mappings = {
        # Food categories
        "food and drink": ["food", "dining", "restaurants", "groceries"],
        "restaurants": ["food", "dining", "restaurants"],
        "fast food": ["food", "dining", "restaurants"],
        "coffee shop": ["food", "dining", "restaurants", "coffee"],
        "bar": ["food", "dining", "entertainment"],
        # Shopping categories
        "shops": ["shopping", "retail"],
        "clothing and accessories": ["shopping", "clothes", "clothing"],
        "general merchandise": ["shopping", "retail"],
        "sporting goods": ["shopping", "sports"],
        "bookstores and newsstands": ["shopping", "books"],
        # Transportation
        "transportation": ["transport", "travel", "gas", "uber", "lyft"],
        "gas stations": ["gas", "transport", "travel"],
        "taxi": ["transport", "uber", "lyft", "travel"],
        "public transportation": ["transport", "travel"],
        "parking": ["transport", "travel"],
        # Entertainment
        "entertainment": ["fun", "movies", "games"],
        "movie theaters": ["entertainment", "movies", "fun"],
        "music and video": ["entertainment", "fun"],
        "gyms and fitness centers": ["fitness", "health", "gym"],
        # Health
        "healthcare services": ["health", "medical", "doctor"],
        "pharmacies": ["health", "medical", "pharmacy"],
        # Utilities & Home
        "utilities": ["bills", "utilities"],
        "internet and cable": ["bills", "utilities", "internet"],
        "mobile phone": ["bills", "utilities", "phone"],
        "rent": ["housing", "rent"],
        "home improvement": ["home", "house"],
        # Financial
        "bank fees": ["fees", "banking"],
        "atm": ["fees", "cash"],
    }

    # Try to find a mapping
    for plaid_cat, possible_matches in category_mappings.items():
        if plaid_cat in plaid_lower:
            for match in possible_matches:
                if match in user_categories:
                    return user_categories[match]

    # If no mapping found, return the original Plaid category
    return plaid_category


def sync_transactions_for_user(user: User):
    """Sync new transactions from Plaid for a user."""
    from plaid.model.transactions_sync_request import TransactionsSyncRequest

    from server import plaid_client

    if not user.plaid_access_token:
        return []

    try:
        cursor = user.plaid_cursor or ""
        new_transactions = []

        request_data = TransactionsSyncRequest(
            access_token=user.plaid_access_token,
            cursor=cursor,
        )
        response = plaid_client.transactions_sync(request_data).to_dict()

        for tx_data in response["added"]:
            # Check if transaction already exists
            existing = Transaction.query.filter_by(
                plaid_transaction_id=tx_data["transaction_id"]
            ).first()

            if not existing:
                # Smart category mapping
                plaid_category = (
                    tx_data["category"][0] if tx_data["category"] else "Other"
                )
                mapped_category = map_plaid_category_to_budget(user, plaid_category)

                transaction = Transaction(
                    user_id=user.id,
                    plaid_transaction_id=tx_data["transaction_id"],
                    merchant_name=tx_data["merchant_name"] or tx_data["name"],
                    amount=abs(
                        Decimal(str(tx_data["amount"]))
                    ),  # Plaid amounts are negative for debits
                    category=mapped_category,
                    original_category=plaid_category,  # Store original Plaid category
                    date=datetime.strptime(tx_data["date"], "%Y-%m-%d").date(),
                    is_pending_review=True,
                    needs_split=False,
                    awaiting_sms_response=True,  # Mark as awaiting SMS response
                )
                db.session.add(transaction)
                new_transactions.append(transaction)

        # Update cursor
        user.plaid_cursor = response["next_cursor"]
        db.session.commit()

        return new_transactions
    except Exception as e:
        logger.error(f"Error syncing transactions: {str(e)}")
        return []


def get_budget_status_text(user: User) -> str:
    """Generate budget status text for SMS."""
    if not user.budget_categories:
        return "💰 No budget set. Set up your budget in the app first!"

    current_month = datetime.now().replace(day=1).date()
    status_lines = ["💰 Budget Status:"]
    total_spent = Decimal("0")
    total_budget = Decimal("0")

    for category in user.budget_categories:
        spent = db.session.query(db.func.sum(Transaction.user_amount)).filter(
            Transaction.user_id == user.id,
            Transaction.category == category.name,
            Transaction.date >= current_month,
            ~Transaction.is_pending_review,
            Transaction.user_amount.isnot(None),
        ).scalar() or Decimal("0")

        remaining = category.monthly_limit - spent
        total_spent += spent
        total_budget += category.monthly_limit

        emoji = "🟢" if remaining > 0 else "🔴"
        status_lines.append(
            f"{emoji} {category.name}: ${spent:.0f}/${category.monthly_limit:.0f}"
        )

    total_remaining = total_budget - total_spent
    status_lines.append(f"\n💳 Total: ${total_spent:.0f}/${total_budget:.0f}")
    status_lines.append(f"💰 Remaining: ${total_remaining:.0f}")

    return "\n".join(status_lines)


def get_pending_transactions_text(user: User) -> str:
    """Generate pending transactions text for SMS."""
    pending = (
        Transaction.query.filter_by(user_id=user.id, is_pending_review=True)
        .order_by(Transaction.date.desc())
        .limit(5)
        .all()
    )

    if not pending:
        return "✅ No pending transactions to review!"

    lines = [f"📋 {len(pending)} pending transactions:"]
    for tx in pending:
        lines.append(
            f"• {tx.merchant_name}: ${tx.amount:.2f} ({tx.date.strftime('%m/%d')})"
        )

    if len(pending) == 5:
        lines.append("\n📱 Use the app to review all transactions.")

    return "\n".join(lines)


def notify_new_transaction(user: User, transaction: Transaction):
    """Send SMS notification for new transaction."""
    # Check if category was auto-mapped vs exact match
    user_category_names = [cat.name.lower() for cat in user.budget_categories]
    is_budget_category = transaction.category.lower() in user_category_names
    category_note = "✅" if is_budget_category else "🤖"

    message = f"""💳 New Transaction:
{transaction.merchant_name}
${transaction.amount:.2f} - {category_note} {transaction.category}
{transaction.date.strftime("%m/%d/%Y")}

Reply: amount,category (e.g. "25,Food") or "full" for ${transaction.amount:.2f}
{category_note} = auto-categorized, ✅ = matches your budget"""

    send_sms(message, user.phone_number)


def process_transaction_response(user: User, message: str) -> str:
    """Process user response to transaction notification."""
    # Get the most recent transaction awaiting response
    pending_tx = (
        Transaction.query.filter_by(user_id=user.id, awaiting_sms_response=True)
        .order_by(Transaction.created_at.desc())
        .first()
    )

    if not pending_tx:
        return "❓ No transaction awaiting response. Text 'help' for commands."

    message = message.strip().lower()

    try:
        # Handle "full" response
        if message == "full":
            pending_tx.user_amount = pending_tx.amount
            pending_tx.needs_split = False

        # Handle amount,category format (e.g. "25,food" or "25")
        elif "," in message:
            parts = message.split(",", 1)
            amount_str = parts[0].strip()
            category_str = parts[1].strip() if len(parts) > 1 else None

            # Parse amount
            try:
                amount = Decimal(amount_str.replace("$", ""))
                pending_tx.user_amount = amount
                pending_tx.needs_split = amount != pending_tx.amount
            except (ValueError, TypeError):
                return f"❌ Invalid amount '{amount_str}'. Try 'full' or a number like '25.50'"

            # Update category if provided
            if category_str:
                # Find matching user budget category
                user_categories = {
                    cat.name.lower(): cat.name for cat in user.budget_categories
                }
                if category_str in user_categories:
                    pending_tx.category = user_categories[category_str]
                else:
                    # Use as-is if not in budget categories
                    pending_tx.category = category_str.title()

        # Handle just amount (e.g. "25")
        else:
            try:
                amount = Decimal(message.replace("$", ""))
                pending_tx.user_amount = amount
                pending_tx.needs_split = amount != pending_tx.amount
            except (ValueError, TypeError):
                return (
                    f"❌ Invalid response '{message}'. Try 'full', '25', or '25,Food'"
                )

        # Mark as reviewed
        pending_tx.is_pending_review = False
        pending_tx.awaiting_sms_response = False
        pending_tx.reviewed_at = datetime.utcnow()
        db.session.commit()

        # Confirmation message
        split_note = (
            f" (split from ${pending_tx.amount:.2f})" if pending_tx.needs_split else ""
        )
        return f"✅ {pending_tx.merchant_name}: ${pending_tx.user_amount:.2f} → {pending_tx.category}{split_note}"

    except Exception as e:
        logger.error(f"Error processing transaction response: {str(e)}")
        return "❌ Error processing response. Try 'full', '25', or '25,Food'"


def sync_all_users():
    """Sync transactions for all users."""
    users = User.query.filter(User.plaid_access_token.isnot(None)).all()
    for user in users:
        try:
            new_transactions = sync_transactions_for_user(user)
            if new_transactions:
                logger.info(
                    f"Synced {len(new_transactions)} new transactions for user {user.phone_number}"
                )
                # Notify user of new transactions
                for tx in new_transactions:
                    notify_new_transaction(user, tx)
        except Exception as e:
            logger.error(
                f"Error syncing transactions for user {user.phone_number}: {str(e)}"
            )
