import plaid
from flask import Flask
from flask_cors import CORS
from plaid.api import plaid_api
from twilio.rest import Client

import config
from models.database import db

# Set up the Plaid environment
host = (
    plaid.Environment.Sandbox
    if config.PLAID_ENV == "sandbox"
    else plaid.Environment.Production
)

# Configure the Plaid client
configuration = plaid.Configuration(
    host=host,
    api_key={
        "clientId": config.PLAID_CLIENT_ID,
        "secret": config.PLAID_SECRET,
        "plaidVersion": "2020-09-14",
    },
)

# Initialize clients
api_client = plaid.ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)
twilio_client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)

# Initialize Flask application
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)

# Initialize database with app
db.init_app(app)

# Initialize the database
with app.app_context():
    db.create_all()
    config.logger.info("Database initialized successfully.")
