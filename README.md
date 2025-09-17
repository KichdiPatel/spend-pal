# SpendPal API


### The Problem
Most budgeting apps/tools are extremely complicated. It makes budgeting too overwhelming for beginners who really just need to get into the routine of being more conscious of their spending. 

### What Spend Pal Does

SpendPal is a SMS-based budget tracker built for beginner budgeters. The idea is to make budgeting as simple as possible in the native SMS app that people open everyday anyway. 

Through the UI, you simply connect your credit card through plaid, and enter your budgets for different categories. Then, you are set! Everything will then be managed through your text messages. Through SMS you can set if a transactions was split amongst friends, and anytime see your current budget status by texting 'budget'.

This is currently only running personally for myself, but the API is built in a way to support multiple users. 


## Tech Stack

- **Backend**: Flask (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **SMS**: Twilio API
- **Banking**: Plaid API
- **Package Management**: Poetry
- **Deployment**: Gunicorn

## QuickStart

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

4. **Set up a database that spendpal can point to, Twilio account, and a Plaid account**

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

   # Database Configuration
   DATABASE_URL=postgresql://username:password@localhost:5432/spendpal
   ```

## Running the Application

### Development
```bash
poetry run gunicorn app:app
```

### Production (Railway)
```bash
poetry run gunicorn --bind 0.0.0.0:$PORT app:app
```

## Code Information

- All routes are set in app.py
- Business logic for all the endpoints are in logic.py
- The database schema is written in database.py
- The API response and request models are in models.py
- The plaid client, twilio client, database, and flask app, are initiliazed in server.py

## Deployment

### Environment Variables
Ensure all required environment variables are set in your production environment. 
At this point, twilio, plaid and, the database should be setup. 


### Railway
I deployed for personal use through Railway. They make it very simple to get started quickly. I can simply connect the github repo I operate out of and deploy from there.
The nixpacks.toml file gives railway instructions on deployment of this project. 

## Future Plans
- The UI is fully vibe coded simply to get Plaid operational and to be able to set/update my budget. So, I would eventually like to turn this into an app where you could complete that setup process. 
- There is no implementation of API Keys right now since I am the only user, but that would be interesting also. 
- Research better practices for storing transactions in a database, since I am storing fields like 'category', 'amount', 'merchant', etc. for max a month. 
