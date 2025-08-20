from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    plaid_access_token = db.Column(db.String(255), nullable=True)
    plaid_item_id = db.Column(db.String(255), nullable=True)
    plaid_cursor = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    budget_categories = db.relationship(
        "BudgetCategory", backref="user", cascade="all, delete-orphan"
    )
    transactions = db.relationship(
        "Transaction", backref="user", cascade="all, delete-orphan"
    )


class BudgetCategory(db.Model):
    __tablename__ = "budget_categories"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    monthly_limit = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Unique constraint per user
    __table_args__ = (
        db.UniqueConstraint("user_id", "name", name="unique_user_category"),
    )


class Transaction(db.Model):
    __tablename__ = "transactions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plaid_transaction_id = db.Column(db.String(255), unique=True, nullable=False)
    merchant_name = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)  # Full transaction amount
    user_amount = db.Column(
        db.Numeric(10, 2), nullable=True
    )  # Amount user actually owes
    category = db.Column(db.String(100), nullable=False)
    original_category = db.Column(
        db.String(100), nullable=True
    )  # Store original Plaid category
    date = db.Column(db.Date, nullable=False)
    is_pending_review = db.Column(db.Boolean, default=True)
    needs_split = db.Column(db.Boolean, default=False)
    awaiting_sms_response = db.Column(
        db.Boolean, default=False
    )  # Track if waiting for SMS response
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
