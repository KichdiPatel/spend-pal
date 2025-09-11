import os

from dotenv import load_dotenv

load_dotenv()

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
PLAID_WEBHOOK_URL = os.getenv("PLAID_WEBHOOK_URL")
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI")
PLAID_CLIENT_NAME = os.getenv("PLAID_CLIENT_NAME", "SpendPal")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 5000))
