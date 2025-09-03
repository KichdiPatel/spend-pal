from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, validator


class CreateLinkTokenRequest(BaseModel):
    """Create Link Token Request.

    Args:
        phone_number: User's phone number
    """

    phone_number: str


class CreateLinkTokenResponse(BaseModel):
    """Create Link Token Response.

    Args:
        link_token: Plaid link token
    """

    link_token: str


class PhoneNumberQuery(BaseModel):
    phone_number: str = Field(..., min_length=10, description="User's phone number")


class ConnectBankRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, description="User's phone number")
    public_token: str = Field(..., description="Plaid public token")


class BudgetLimitsRequest(BaseModel):
    """Budget limits for each Plaid category (1:1 naming convention)."""

    income_budget: Decimal = Field(0, ge=0, description="Income budget")
    transfer_in_budget: Decimal = Field(0, ge=0, description="Transfer in budget")
    transfer_out_budget: Decimal = Field(0, ge=0, description="Transfer out budget")
    loan_payments_budget: Decimal = Field(0, ge=0, description="Loan payments budget")
    bank_fees_budget: Decimal = Field(0, ge=0, description="Bank fees budget")
    entertainment_budget: Decimal = Field(0, ge=0, description="Entertainment budget")
    food_and_drink_budget: Decimal = Field(0, ge=0, description="Food & drink budget")
    general_merchandise_budget: Decimal = Field(0, ge=0, description="Shopping budget")
    home_improvement_budget: Decimal = Field(
        0, ge=0, description="Home improvement budget"
    )
    medical_budget: Decimal = Field(0, ge=0, description="Medical budget")
    personal_care_budget: Decimal = Field(0, ge=0, description="Personal care budget")
    general_services_budget: Decimal = Field(
        0, ge=0, description="General services budget"
    )
    government_and_non_profit_budget: Decimal = Field(
        0, ge=0, description="Government & non-profit budget"
    )
    transportation_budget: Decimal = Field(0, ge=0, description="Transportation budget")
    travel_budget: Decimal = Field(0, ge=0, description="Travel budget")
    rent_and_utilities_budget: Decimal = Field(
        0, ge=0, description="Rent & utilities budget"
    )

    @validator("*")
    def validate_decimal(cls, v):
        """Ensure all values are valid decimals."""
        if v is None:
            return Decimal("0")
        return v


class SetBudgetRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, description="User's phone number")
    budget_limits: BudgetLimitsRequest = Field(
        ..., description="Budget limits by Plaid category"
    )


class TransactionVerificationRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, description="User's phone number")
    transaction_id: str = Field(..., description="Plaid transaction ID")
    user_amount: Decimal = Field(..., gt=0, description="Amount user actually paid")
    category_override: Optional[str] = Field(
        None, description="Override Plaid category"
    )


# Response Models
class BudgetCategoryResponse(BaseModel):
    category: str
    monthly_limit: float
    spent: float
    remaining: float


class BudgetResponse(BaseModel):
    budget: list[BudgetCategoryResponse]


class MonthlyTotalsResponse(BaseModel):
    """Monthly spending totals by Plaid category."""

    income: float
    transfer_in: float
    transfer_out: float
    loan_payments: float
    bank_fees: float
    entertainment: float
    food_and_drink: float
    general_merchandise: float
    home_improvement: float
    medical: float
    personal_care: float
    general_services: float
    government_and_non_profit: float
    transportation: float
    travel: float
    rent_and_utilities: float


class PendingTransactionResponse(BaseModel):
    id: str
    merchant_name: str
    amount: float
    category: str
    date: str
    original_category: str


class PendingTransactionsResponse(BaseModel):
    pending_transactions: list[PendingTransactionResponse]


class CategoriesResponse(BaseModel):
    categories: list[str]


class SuccessResponse(BaseModel):
    status: str
