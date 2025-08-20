import logging
import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Plaid Configuration
PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")
PLAID_WEBHOOK_URL = os.getenv("PLAID_WEBHOOK_URL")
PLAID_REDIRECT_URI = os.getenv("PLAID_REDIRECT_URI")
PLAID_CLIENT_NAME = os.getenv("PLAID_CLIENT_NAME", "SpendPal")

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
USER_PHONE_NUMBER = os.getenv("USER_PHONE_NUMBER")

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
PORT = int(os.getenv("PORT", 5000))

# Verify required environment variables
required_vars = {
    "DATABASE_URL": DATABASE_URL,
    "PLAID_CLIENT_ID": PLAID_CLIENT_ID,
    "PLAID_SECRET": PLAID_SECRET,
    "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
    "TWILIO_AUTH_TOKEN": TWILIO_AUTH_TOKEN,
    "TWILIO_PHONE_NUMBER": TWILIO_PHONE_NUMBER,
    "USER_PHONE_NUMBER": USER_PHONE_NUMBER,
}

for var_name, var_value in required_vars.items():
    if not var_value:
        logger.error(f"{var_name} is not set or is empty.")
        exit(1)

logger.info("Configuration loaded successfully")
