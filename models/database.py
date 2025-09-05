from datetime import datetime

from sqlalchemy import event

from server import db

# TODO: maybe remove the updated_at, create_at, last_sync_date, etc.


class User(db.Model):
    """User model with Plaid integration and basic user information."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    plaid_access_token = db.Column(db.String(255), nullable=False)
    plaid_item_id = db.Column(db.String(255), nullable=False)
    plaid_cursor = db.Column(db.String(255), nullable=False)
    last_sync_date = db.Column(db.Date, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.now(datetime.timezone.utc))

    currently_reconciling = db.Column(db.Boolean, default=False)
    reconcile_category = db.Column(db.String(255), nullable=True)
    reconcile_amount = db.Column(db.Numeric(10, 2), nullable=True)
    reconcile_transaction_id = db.Column(db.String(255), nullable=True)
    transaction_queue = db.Column(
        db.JSON, nullable=True, default=list
    )  # List of transaction IDs to process

    # Relationships
    monthly_spending = db.relationship(
        "MonthlySpending",
        uselist=False,
        cascade="all, delete-orphan",
    )
    budgets = db.relationship("Budget", uselist=False, cascade="all, delete-orphan")


class MonthlySpending(db.Model):
    """Monthly spending totals by Plaid category."""

    __tablename__ = "monthly_spending"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)

    income = db.Column(db.Numeric(10, 2))
    transfer_in = db.Column(db.Numeric(10, 2))
    transfer_out = db.Column(db.Numeric(10, 2))
    loan_payments = db.Column(db.Numeric(10, 2))
    bank_fees = db.Column(db.Numeric(10, 2))
    entertainment = db.Column(db.Numeric(10, 2))
    food_and_drink = db.Column(db.Numeric(10, 2))
    general_merchandise = db.Column(db.Numeric(10, 2))
    home_improvement = db.Column(db.Numeric(10, 2))
    medical = db.Column(db.Numeric(10, 2))
    personal_care = db.Column(db.Numeric(10, 2))
    general_services = db.Column(db.Numeric(10, 2))
    government_and_non_profit = db.Column(db.Numeric(10, 2))
    transportation = db.Column(db.Numeric(10, 2))
    travel = db.Column(db.Numeric(10, 2))
    rent_and_utilities = db.Column(db.Numeric(10, 2))

    created_at = db.Column(db.DateTime, default=datetime.now(datetime.timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(datetime.timezone.utc),
        onupdate=datetime.now(datetime.timezone.utc),
    )


class Budget(db.Model):
    """Monthly budget limits by Plaid category."""

    __tablename__ = "budgets"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)

    income = db.Column(db.Numeric(10, 2))
    transfer_in = db.Column(db.Numeric(10, 2))
    transfer_out = db.Column(db.Numeric(10, 2))
    loan_payments = db.Column(db.Numeric(10, 2))
    bank_fees = db.Column(db.Numeric(10, 2))
    entertainment = db.Column(db.Numeric(10, 2))
    food_and_drink = db.Column(db.Numeric(10, 2))
    general_merchandise = db.Column(db.Numeric(10, 2))
    home_improvement = db.Column(db.Numeric(10, 2))
    medical = db.Column(db.Numeric(10, 2))
    personal_care = db.Column(db.Numeric(10, 2))
    general_services = db.Column(db.Numeric(10, 2))
    government_and_non_profit = db.Column(db.Numeric(10, 2))
    transportation = db.Column(db.Numeric(10, 2))
    travel = db.Column(db.Numeric(10, 2))
    rent_and_utilities = db.Column(db.Numeric(10, 2))

    created_at = db.Column(db.DateTime, default=datetime.now(datetime.timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=datetime.now(datetime.timezone.utc),
        onupdate=datetime.now(datetime.timezone.utc),
    )


@event.listens_for(User, "after_insert")
def create_user_records(mapper, connection, target):
    """Create Budget and MonthlySpending records immediately after User creation."""

    budget = Budget(user_id=target.id)
    connection.add(budget)

    monthly_spending = MonthlySpending(user_id=target.id)
    connection.add(monthly_spending)
