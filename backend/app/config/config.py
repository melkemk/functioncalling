import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# API credentials
EXCHANGE_RATE_API_URL = "https://v6.exchangerate-api.com/v6/"
EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Database configuration
SQLALCHEMY_DATABASE_URI = 'sqlite:///financial_assistant.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

# Validate required environment variables
def validate_config():
    if not GEMINI_API_KEY:
        logging.error("GEMINI_API_KEY not found in environment variables. AI features will be disabled.")
    
    if not EXCHANGE_RATE_API_KEY:
        logging.warning("EXCHANGE_RATE_API_KEY not found. Exchange rate functionality will be impaired.")
    
    if not SECRET_KEY or SECRET_KEY == 'your-secret-key-here':
        logging.warning("Using default SECRET_KEY. This is not secure for production.")

# Initialize configuration
validate_config() 