from pydantic import BaseModel


class CreateLinkTokenRequest(BaseModel):
    """Create Link Token Request.

    Args:
        phone_number: User's phone number.
    """

    phone_number: str


class CreateLinkTokenResponse(BaseModel):
    """Create Link Token Response.

    Args:
        link_token: Plaid link token.
    """

    link_token: str


class ConnectBankRequest(BaseModel):
    """Connect Bank Request.

    Args:
        phone_number: User's phone number.
        public_token: Plaid public token.
    """

    phone_number: str
    public_token: str
    public_token: str


class DeleteUserRequest(BaseModel):
    """Delete User Request.

    Args:
        phone_number: User's phone number.
    """

    phone_number: str


class GetBudgetDataRequest(BaseModel):
    """Get Budget Request.

    Args:
        phone_number: User's phone number.
    """

    phone_number: str


class GetBudgetDataResponse(BaseModel):
    """Get Budget Response.

    Args:
        budgets: budgets for each Plaid category.
        monthly_totals: total monthly spend for each Plaid category.
    """

    class Categories(BaseModel):
        """Plaid categories.

        Args:
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

        income: float = 0.0
        transfer_in: float = 0.0
        transfer_out: float = 0.0
        loan_payments: float = 0.0
        bank_fees: float = 0.0
        entertainment: float = 0.0
        food_and_drink: float = 0.0
        general_merchandise: float = 0.0
        home_improvement: float = 0.0
        medical: float = 0.0
        personal_care: float = 0.0
        general_services: float = 0.0
        government_and_non_profit: float = 0.0
        transportation: float = 0.0
        travel: float = 0.0
        rent_and_utilities: float = 0.0

    budgets: Categories
    monthly_totals: Categories


class UpdateBudgetRequest(BaseModel):
    """Update Budget Request.

    Args:
        phone_number: User's phone number.
        budgets: Budget limits for each Plaid category.
    """

    class Budgets(BaseModel):
        """Budgets for each Plaid category.

        Args:
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

        income: float | None = None
        transfer_in: float | None = None
        transfer_out: float | None = None
        loan_payments: float | None = None
        bank_fees: float | None = None
        entertainment: float | None = None
        food_and_drink: float | None = None
        general_merchandise: float | None = None
        home_improvement: float | None = None
        medical: float | None = None
        personal_care: float | None = None
        general_services: float | None = None
        government_and_non_profit: float | None = None
        transportation: float | None = None
        travel: float | None = None
        rent_and_utilities: float | None = None

    phone_number: str
    budgets: Budgets


class GeneralResponse(BaseModel):
    """General Response.

    Args:
        message: Message.
    """

    message: str
