from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# TODO: add a budget table, and monthly totals table
class User(db.Model):
    """User model with Plaid integration and monthly budget tracking."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    plaid_access_token = db.Column(db.String(255), nullable=True)
    plaid_item_id = db.Column(db.String(255), nullable=True)
    plaid_cursor = db.Column(db.String(255), nullable=True)
    last_sync_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Current month spending totals by Plaid category
    income_total = db.Column(db.Numeric(10, 2))  # 10 total digits, 2 decimal places
    transfer_in_total = db.Column(db.Numeric(10, 2))
    transfer_out_total = db.Column(db.Numeric(10, 2))
    loan_payments_total = db.Column(db.Numeric(10, 2))
    bank_fees_total = db.Column(db.Numeric(10, 2))
    entertainment_total = db.Column(db.Numeric(10, 2))
    food_and_drink_total = db.Column(db.Numeric(10, 2))
    general_merchandise_total = db.Column(db.Numeric(10, 2))
    home_improvement_total = db.Column(db.Numeric(10, 2))
    medical_total = db.Column(db.Numeric(10, 2))
    personal_care_total = db.Column(db.Numeric(10, 2))
    general_services_total = db.Column(db.Numeric(10, 2))
    government_and_non_profit_total = db.Column(db.Numeric(10, 2))
    transportation_total = db.Column(db.Numeric(10, 2))
    travel_total = db.Column(db.Numeric(10, 2))
    rent_and_utilities_total = db.Column(db.Numeric(10, 2))

    # Monthly budget limits
    income_budget = db.Column(db.Numeric(10, 2))
    transfer_in_budget = db.Column(db.Numeric(10, 2))
    transfer_out_budget = db.Column(db.Numeric(10, 2))
    loan_payments_budget = db.Column(db.Numeric(10, 2))
    bank_fees_budget = db.Column(db.Numeric(10, 2))
    entertainment_budget = db.Column(db.Numeric(10, 2))
    food_and_drink_budget = db.Column(db.Numeric(10, 2))
    general_merchandise_budget = db.Column(db.Numeric(10, 2))
    home_improvement_budget = db.Column(db.Numeric(10, 2))
    medical_budget = db.Column(db.Numeric(10, 2))
    personal_care_budget = db.Column(db.Numeric(10, 2))
    general_services_budget = db.Column(db.Numeric(10, 2))
    government_and_non_profit_budget = db.Column(db.Numeric(10, 2))
    transportation_budget = db.Column(db.Numeric(10, 2))
    travel_budget = db.Column(db.Numeric(10, 2))
    rent_and_utilities_budget = db.Column(db.Numeric(10, 2))
