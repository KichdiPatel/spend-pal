# SpendPal API

A simple SMS-based budget tracking API with Plaid integration for bank account connection and smart transaction splitting.

## Features

- **SMS Interface**: Manage your budget via text messages
- **Plaid Integration**: Connect bank accounts and sync transactions automatically
- **Smart Transaction Splitting**: Handle shared expenses and bill splitting
- **Budget Tracking**: Set monthly budget limits and get real-time status
- **Automated Notifications**: Get SMS alerts for new transactions
- **RESTful API**: Clean API endpoints for frontend integration

## Tech Stack

- **Backend**: Flask (Python) with modular architecture
- **Database**: PostgreSQL with SQLAlchemy ORM
- **SMS**: Twilio API
- **Banking**: Plaid API
- **Package Management**: Poetry
- **Deployment**: Gunicorn

## Project Structure

```
spend-pal-api/
├── app.py          # Main Flask routes and API endpoints
├── config.py       # Environment variables and configuration
├── models.py       # Database models (User, Transaction, BudgetCategory)
├── server.py       # Flask app initialization and client setup
├── utils.py        # Helper functions and business logic
├── pyproject.toml  # Poetry configuration
├── README.md       # Documentation
└── templates/
    └── index.html  # Plaid Link integration page
```

## Prerequisites

- Python 3.9+
- PostgreSQL database
- Plaid account and API credentials
- Twilio account and phone number
- Poetry (for dependency management)

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd spend-pal-api
   ```

2. **Install Poetry** (if not already installed)
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. **Install dependencies**
   ```bash
   poetry install
   ```

4. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```env
   # Plaid Configuration
   PLAID_CLIENT_ID=your_plaid_client_id
   PLAID_SECRET=your_plaid_secret
   PLAID_ENV=sandbox
   PLAID_WEBHOOK_URL=your_webhook_url
   PLAID_REDIRECT_URI=your_redirect_uri
   PLAID_CLIENT_NAME=SpendPal

   # Twilio Configuration
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_PHONE_NUMBER=+1234567890
   USER_PHONE_NUMBER=+1987654321

   # Database Configuration
   DATABASE_URL=postgresql://username:password@localhost:5432/spendpal

   # Server Configuration
   PORT=5000
   ```

5. **Set up the database**
   ```bash
   # Create PostgreSQL database
   createdb spendpal

   # Run the application to create tables
   poetry run python app.py
   ```

## Running the Application

### Development
```bash
poetry run python app.py
```

### Production
```bash
poetry run gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## API Endpoints

### Bank Account Setup
- `POST /api/create_link_token` - Create Plaid Link token for bank connection
- `POST /api/connect_bank` - Connect bank account using public token

### Budget Management
- `GET /api/budget?phone_number={phone}` - Get budget categories and spending
- `POST /api/budget` - Set budget categories for a user

### Transaction Management
- `GET /api/transactions/pending?phone_number={phone}` - Get transactions needing review
- `POST /api/transactions/{id}/review` - Review and approve a transaction
- `GET /api/categories?phone_number={phone}` - Get available categories for override

### SMS Interface
- `POST /sms` - Handle incoming SMS messages (Twilio webhook)

### System
- `GET /api/health` - Health check endpoint

## SMS Commands

Text these commands to your Twilio phone number:
- **help** - Show available commands
- **balance** - See your current budget status
- **pending** - View transactions needing review
- **sync** - Manually sync new transactions

### Transaction Response Format
When you receive a transaction notification, reply with:
- **full** - You owe the full amount
- **25** - You owe $25 (keeps auto-assigned category)
- **25,Food** - You owe $25 and change category to "Food"
- **0** - You don't owe anything (someone else paid)

## Smart Categorization

SpendPal automatically categorizes transactions using:

1. **Direct Match**: If Plaid's category matches your budget category exactly
2. **Smart Mapping**: Maps Plaid categories to your budget categories:
   - "Restaurants" → "Food" (if you have a "Food" budget)
   - "Gas Stations" → "Transport" (if you have a "Transport" budget)
   - "General Merchandise" → "Shopping" (if you have a "Shopping" budget)
3. **Fallback**: Uses Plaid's original category if no mapping found

### Category Override Options
- **Budget Categories**: Your custom categories (preferred, count toward budget)
- **Standard Categories**: Common categories for transactions outside your budget

## Database Schema

### Users Table
- `id`: Primary key
- `phone_number`: User's phone number (unique)
- `plaid_access_token`: Plaid access token
- `plaid_item_id`: Plaid item ID
- `plaid_cursor`: Transaction sync cursor
- `created_at`: Account creation timestamp

### Budget Categories Table
- `id`: Primary key
- `user_id`: Foreign key to users table
- `name`: Category name (e.g., "Food", "Shopping")
- `monthly_limit`: Monthly spending limit
- `created_at`: Category creation timestamp

### Transactions Table
- `id`: Primary key
- `user_id`: Foreign key to users table
- `plaid_transaction_id`: Plaid transaction ID (unique)
- `merchant_name`: Merchant/vendor name
- `amount`: Full transaction amount
- `user_amount`: Amount user actually owes (for split transactions)
- `category`: Transaction category
- `date`: Transaction date
- `is_pending_review`: Whether transaction needs user review
- `needs_split`: Whether transaction was split with others
- `created_at`: Record creation timestamp
- `reviewed_at`: When transaction was reviewed

## Development

### Code Formatting
```bash
poetry run black .
poetry run flake8 .
poetry run mypy .
```

### Testing
```bash
poetry run pytest
```

## Deployment

### Environment Variables
Ensure all required environment variables are set in your production environment.

### Database
- Use a production PostgreSQL instance
- Set up proper backups
- Configure connection pooling

### Process Management
- Use a process manager like PM2 or systemd
- Set up proper logging
- Configure monitoring and alerting

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license here]

## Support

For support, please open an issue in the GitHub repository.
