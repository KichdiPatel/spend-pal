import plaid
from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from loguru import logger
from plaid.api import plaid_api
from twilio.rest import Client

import config

db = SQLAlchemy()


# Set up the Plaid client
host = (
    plaid.Environment.Sandbox
    if config.PLAID_ENV == "sandbox"
    else plaid.Environment.Production
)

configuration = plaid.Configuration(
    host=host,
    api_key={
        "clientId": config.PLAID_CLIENT_ID,
        "secret": config.PLAID_SECRET,
        "plaidVersion": "2020-09-14",
    },
)

api_client = plaid.ApiClient(configuration)
plaid_client = plaid_api.PlaidApi(api_client)


# Initialize Twilio client
twilio_client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)


# Initialize Flask app
app = Flask(__name__)


@app.errorhandler(Exception)
def handle_exception(e):
    """Log all unhandled exceptions."""
    logger.exception("Unhandled exception occurred")
    return "Internal Server Error", 500


# Initialize Database with app
app.config["SQLALCHEMY_DATABASE_URI"] = config.DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
CORS(app)

db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    logger.info("Database initialized successfully.")
