from models.database import User
from server import db


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


# TODO: SMS logic
