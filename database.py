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
    # transaction_queue = db.Column(
    #     MutableList.as_mutable(JSON), nullable=True, default=list
    # )
    # current_month = db.Column(db.Date, default=datetime.now().date())

    transactions = db.relationship(
        "Transactions", backref="user", cascade="all, delete-orphan"
    )
    budgets = db.relationship("Budget", uselist=False, cascade="all, delete-orphan")


class Transactions(db.Model):
    """Transactions for the current month recorded for all users.

    Args:
        user_id: User id.
        amount: Transaction amount.
        tx_id: Transaction id.
        plaid_category: Plaid category.
        date: Transaction date.
        merchant_name: Transaction merchant name.
        reconciled: Whether the transaction has been reconciled.
    """

    __tablename__ = "Transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount = db.Column(db.Numeric(10, 2), default=0)
    tx_id = db.Column(db.String(255), nullable=False)
    plaid_category = db.Column(db.String(255), nullable=False)
    date = db.Column(db.Date, nullable=False)
    merchant_name = db.Column(db.String(255), nullable=False)
    reconciled = db.Column(db.Boolean, default=False)


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

    __tablename__ = "Budget"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    income = db.Column(db.Numeric(10, 2), default=0)
    transfer_in = db.Column(db.Numeric(10, 2), default=0)
    transfer_out = db.Column(db.Numeric(10, 2), default=0)
    loan_payments = db.Column(db.Numeric(10, 2), default=0)
    bank_fees = db.Column(db.Numeric(10, 2), default=0)
    entertainment = db.Column(db.Numeric(10, 2), default=0)
    food_and_drink = db.Column(db.Numeric(10, 2), default=0)
    general_merchandise = db.Column(db.Numeric(10, 2), default=0)
    home_improvement = db.Column(db.Numeric(10, 2), default=0)
    medical = db.Column(db.Numeric(10, 2), default=0)
    personal_care = db.Column(db.Numeric(10, 2), default=0)
    general_services = db.Column(db.Numeric(10, 2), default=0)
    government_and_non_profit = db.Column(db.Numeric(10, 2), default=0)
    transportation = db.Column(db.Numeric(10, 2), default=0)
    travel = db.Column(db.Numeric(10, 2), default=0)
    rent_and_utilities = db.Column(db.Numeric(10, 2), default=0)
