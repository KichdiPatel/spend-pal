import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

import config
from models.database import User, db
from server import plaid_client, twilio_client

logger = logging.getLogger(__name__)


def get_plaid_category_field(plaid_category: str) -> str:
    """Map Plaid category to database field name."""
    category_mapping = {
        "income": "income_total",
        "transfer_in": "transfer_in_total",
        "transfer_out": "transfer_out_total",
        "loan_payments": "loan_payments_total",
        "bank_fees": "bank_fees_total",
        "entertainment": "entertainment_total",
        "food_and_drink": "food_and_drink_total",
        "general_merchandise": "general_merchandise_total",
        "home_improvement": "home_improvement_total",
        "medical": "medical_total",
        "personal_care": "personal_care_total",
        "general_services": "general_services_total",
        "government_and_non_profit": "government_and_non_profit_total",
        "transportation": "transportation_total",
        "travel": "travel_total",
        "rent_and_utilities": "rent_and_utilities_total",
    }
    return category_mapping.get(plaid_category, "general_merchandise_total")


def update_monthly_totals(user: User, plaid_category: str, amount: Decimal):
    """Update monthly total for a specific Plaid category."""
    field_name = get_plaid_category_field(plaid_category)
    current_total = getattr(user, field_name, Decimal("0"))
    setattr(user, field_name, current_total + amount)


def reset_monthly_totals(user: User):
    """Reset all monthly totals to zero (call at start of new month)."""
    category_fields = [
        "income_total",
        "transfer_in_total",
        "transfer_out_total",
        "loan_payments_total",
        "bank_fees_total",
        "entertainment_total",
        "food_and_drink_total",
        "general_merchandise_total",
        "home_improvement_total",
        "medical_total",
        "personal_care_total",
        "general_services_total",
        "government_and_non_profit_total",
        "transportation_total",
        "travel_total",
        "rent_and_utilities_total",
    ]

    for field in category_fields:
        setattr(user, field, Decimal("0.00"))


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

    # Direct mapping to our field names - much simpler!
    plaid_to_budget_mapping = {
        "income": "income",
        "transfer_in": "transfer_in",
        "transfer_out": "transfer_out",
        "loan_payments": "loan_payments",
        "bank_fees": "bank_fees",
        "entertainment": "entertainment",
        "food_and_drink": "food_and_drink",
        "general_merchandise": "general_merchandise",
        "home_improvement": "home_improvement",
        "medical": "medical",
        "personal_care": "personal_care",
        "general_services": "general_services",
        "government_and_non_profit": "government_and_non_profit",
        "transportation": "transportation",
        "travel": "travel",
        "rent_and_utilities": "rent_and_utilities",
    }

    # Return mapped category or fallback to general_merchandise
    return plaid_to_budget_mapping.get(plaid_category.lower(), "general_merchandise")


def get_pending_transactions_for_verification(user: User) -> List[Dict[str, Any]]:
    """Get transactions that need user verification for amount adjustment."""
    if not user.plaid_access_token:
        return []

    try:
        # Get current month boundaries
        now = datetime.now()
        current_month_start = date(now.year, now.month, 1)
        current_month_end = (
            date(now.year, now.month + 1, 1)
            if now.month < 12
            else date(now.year + 1, 1, 1)
        )

        # Use cursor-based syncing to get all transactions
        cursor = user.plaid_cursor or ""
        pending_transactions = []

        while True:
            from plaid.model.transactions_sync_request import TransactionsSyncRequest

            request_data = TransactionsSyncRequest(
                access_token=user.plaid_access_token,
                cursor=cursor,
            )
            response = plaid_client.transactions_sync(request_data).to_dict()

            # Process added transactions
            for tx_data in response["added"]:
                tx_date = datetime.strptime(tx_data["date"], "%Y-%m-%d").date()

                # Only include transactions from current month
                if current_month_start <= tx_date < current_month_end:
                    # Smart category mapping
                    plaid_category = (
                        tx_data["category"][0] if tx_data["category"] else "Other"
                    )
                    mapped_category = map_plaid_category_to_budget(user, plaid_category)

                    transaction = {
                        "id": tx_data["transaction_id"],
                        "merchant_name": tx_data["merchant_name"] or tx_data["name"],
                        "amount": abs(
                            Decimal(str(tx_data["amount"]))
                        ),  # Plaid amounts are negative for debits
                        "category": mapped_category,
                        "original_category": plaid_category,
                        "date": tx_data["date"],
                        "date_obj": tx_date,
                    }
                    pending_transactions.append(transaction)

            # Update cursor for next iteration
            cursor = response["next_cursor"]

            # Break if no more transactions or if we've reached the end
            if not response["added"] or cursor == user.plaid_cursor:
                break

        return pending_transactions

    except Exception as e:
        logger.error(
            f"Error getting pending transactions for user {user.phone_number}: {str(e)}"
        )
        return []


def get_current_month_transactions(user: User) -> List[Dict[str, Any]]:
    """Get all transactions for the current month from Plaid and update monthly totals."""
    if not user.plaid_access_token:
        return []

    try:
        # Check if we need to reset monthly totals (new month)
        now = datetime.now()
        current_month_start = date(now.year, now.month, 1)

        if user.last_sync_date is None or user.last_sync_date < current_month_start:
            reset_monthly_totals(user)
            user.last_sync_date = current_month_start
            logger.info(f"Reset monthly totals for user {user.phone_number}")

        # Get pending transactions for verification
        pending_transactions = get_pending_transactions_for_verification(user)

        # Update user's cursor to latest position
        if pending_transactions:
            # Note: In a real implementation, you'd want to store the cursor
            # after user verification, not here
            pass

        return pending_transactions

    except Exception as e:
        logger.error(
            f"Error getting transactions for user {user.phone_number}: {str(e)}"
        )
        return []


def get_budget_status_text(user: User) -> str:
    """Generate budget status text for SMS showing spend vs budget with percentages for categories with spending > 0."""
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

    # Filter to only show categories where current spend > 0
    categories_with_spending = [
        (name, budget, total)
        for name, budget, total in budget_mapping
        if (total or Decimal("0")) > 0
    ]

    if not categories_with_spending:
        return "💰 No spending this month yet!"

    status_lines = ["💰 Budget Status (Categories with Spending):"]
    total_spent = Decimal("0")
    total_budget = Decimal("0")

    # Show spend vs budget with percentages
    for name, budget_limit, spent in categories_with_spending:
        spent = spent or Decimal("0")
        budget_limit = budget_limit or Decimal("0")

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

    # Add summary
    if total_budget > 0:
        overall_percentage = (total_spent / total_budget) * 100
        status_lines.append(
            f"\n💳 Total: ${total_spent:.2f}/${total_budget:.2f} ({overall_percentage:.1f}%)"
        )
    else:
        status_lines.append(f"\n💳 Total Spent: ${total_spent:.2f} (no budgets set)")

    return "\n".join(status_lines)


def get_pending_transactions_text(user: User) -> str:
    """Generate text showing transactions pending verification."""
    pending_transactions = get_pending_transactions_for_verification(user)

    if not pending_transactions:
        return "✅ No transactions pending verification!"

    lines = [f"📋 {len(pending_transactions)} transactions need verification:"]

    for tx in pending_transactions[:5]:  # Show first 5
        lines.append(f"• {tx['merchant_name']}: ${tx['amount']:.2f} ({tx['date']})")

    if len(pending_transactions) > 5:
        lines.append(
            f"\n📱 Use the app to verify all {len(pending_transactions)} transactions"
        )

    return "\n".join(lines)


def get_recent_transactions_text(user: User, limit: int = 5) -> str:
    """Generate recent transactions text for SMS using stored monthly totals."""
    # For now, just show the monthly totals by category
    # In a real implementation, you might want to show recent individual transactions
    # that the user has verified

    lines = ["📋 Monthly Spending by Category:"]

    # Show top spending categories
    category_totals = [
        ("Food & Drink", user.food_and_drink_total),
        ("Shopping", user.general_merchandise_total),
        ("Transportation", user.transportation_total),
        ("Entertainment", user.entertainment_total),
        ("Medical", user.medical_total),
        ("Utilities", user.rent_and_utilities_total),
    ]

    # Sort by amount and show top categories
    sorted_categories = sorted(category_totals, key=lambda x: x[1], reverse=True)

    for name, total in sorted_categories[:limit]:
        if total > 0:
            lines.append(f"• {name}: ${total:.2f}")

    if not any(total > 0 for _, total in sorted_categories):
        lines.append("✅ No spending recorded this month")

    return "\n".join(lines)


def sync_user_transactions(user: User):
    """Sync transactions for a specific user and update monthly totals."""
    try:
        # Get transactions and update monthly totals
        transactions = get_current_month_transactions(user)
        if transactions:
            logger.info(
                f"Updated monthly totals for user {user.phone_number} - found {len(transactions)} transactions"
            )
        return True
    except Exception as e:
        logger.error(
            f"Error syncing transactions for user {user.phone_number}: {str(e)}"
        )
        return False


def sync_all_users():
    """Sync transactions for all users (now just updates cursors and monthly totals)."""
    users = User.query.filter(User.plaid_access_token.isnot(None)).all()
    for user in users:
        sync_user_transactions(user)
