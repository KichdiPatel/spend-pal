from sqlalchemy import event

from server import db


class User(db.Model):
    """User model with Plaid integration and basic user information.

    Args:
        id: User id.
        phone_number: User's phone number.
        plaid_access_token: Plaid access token.
        plaid_item_id: Plaid item id.
        plaid_cursor: Plaid cursor.
        current_reconciling_tx_id: Current reconciling transaction id.
        transaction_queue: Transaction queue.
        current_month: Current month.
    """

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    plaid_access_token = db.Column(db.String(255), nullable=False)
    plaid_item_id = db.Column(db.String(255), nullable=False)
    plaid_cursor = db.Column(db.String(255), nullable=False)

    current_reconciling_tx_id = db.Column(db.String(255), nullable=True)
    transaction_queue = db.Column(db.JSON, nullable=True, default=list)
    current_month = db.Column(db.Date, nullable=True)

    monthly_spending = db.relationship(
        "MonthlySpending", uselist=False, cascade="all, delete-orphan"
    )
    budgets = db.relationship("Budget", uselist=False, cascade="all, delete-orphan")


class MonthlySpending(db.Model):
    """Monthly spending totals by Plaid category.

    Args:
        user_id: User id.
        income: Income.
        transfer_in: Transfer in.
        transfer_out: Transfer out.
        loan_payments: Loan payments.
        bank_fees: Bank fees.
        entertainment: Entertainment.
        food_and_drink: Food and drink.
        general_merchandise: General merchandise.
        home_improvement: Home improvement.
        medical: Medical.
        personal_care: Personal care.
        general_services: General services.
        government_and_non_profit: Government and non-profit.
        transportation: Transportation.
        travel: Travel.
        rent_and_utilities: Rent and utilities.
    """

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


class Budget(db.Model):
    """Monthly budget limits by Plaid category.

    Args:
        user_id: User id.
        income: Income.
        transfer_in: Transfer in.
        transfer_out: Transfer out.
        loan_payments: Loan payments.
        bank_fees: Bank fees.
        entertainment: Entertainment.
        food_and_drink: Food and drink.
        general_merchandise: General merchandise.
        home_improvement: Home improvement.
        medical: Medical.
        personal_care: Personal care.
        general_services: General services.
        government_and_non_profit: Government and non-profit.
        transportation: Transportation.
        travel: Travel.
        rent_and_utilities: Rent and utilities.
    """

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


@event.listens_for(User, "after_insert")
def create_user_records(mapper, connection, target):
    """Create Budget and MonthlySpending records immediately after User creation."""

    budget = Budget(user_id=target.id)
    connection.add(budget)

    monthly_spending = MonthlySpending(user_id=target.id)
    connection.add(monthly_spending)
