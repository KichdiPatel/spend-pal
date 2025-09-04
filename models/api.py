from pydantic import BaseModel


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


class ConnectBankRequest(BaseModel):
    """Connect Bank Request.

    Args:
        phone_number: User's phone number
        public_token: Plaid public token
    """

    phone_number: str
    public_token: str


class GetBudgetDataRequest(BaseModel):
    """Get Budget Request.

    Args:
        phone_number: User's phone number
    """

    phone_number: str


class GetBudgetDataResponse(BaseModel):
    """Get Budget Response.

    Args:
        budgets: budgets for each Plaid category
        monthly_totals: total monthly spend for each Plaid category
    """

    class Categories(BaseModel):
        """Plaid categories.

        Args:
            income: Income
            transfer_in: Transfer in
            transfer_out: Transfer out
            loan_payments: Loan payments
            bank_fees: Bank fees
            entertainment: Entertainment
            food_and_drink: Food and drink
            general_merchandise: General merchandise
            home_improvement: Home improvement
            medical: Medical
            personal_care: Personal care
            general_services: General services
            government_and_non_profit: Government and non-profit
            transportation: Transportation
            travel: Travel
            rent_and_utilities: Rent and utilities
        """

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

    budgets: Categories
    monthly_totals: Categories


class UpdateBudgetRequest(BaseModel):
    """Update Budget Request.

    Args:
        phone_number: User's phone number
        budgets: Budget limits for each Plaid category
    """

    class Budgets(BaseModel):
        """Budgets for each Plaid category.

        Args:
            income: Income
            transfer_in: Transfer in
            transfer_out: Transfer out
            loan_payments: Loan payments
            bank_fees: Bank fees
            entertainment: Entertainment
            food_and_drink: Food and drink
            general_merchandise: General merchandise
            home_improvement: Home improvement
            medical: Medical
            personal_care: Personal care
            general_services: General services
            government_and_non_profit: Government and non-profit
            transportation: Transportation
            travel: Travel
            rent_and_utilities: Rent and utilities
        """

        income: float | None
        transfer_in: float | None
        transfer_out: float | None
        loan_payments: float | None
        bank_fees: float | None
        entertainment: float | None
        food_and_drink: float | None
        general_merchandise: float | None
        home_improvement: float | None
        medical: float | None
        personal_care: float | None
        general_services: float | None
        government_and_non_profit: float | None
        transportation: float | None
        travel: float | None
        rent_and_utilities: float | None

    phone_number: str
    budgets: Budgets
