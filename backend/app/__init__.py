# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging
import google.generativeai as genai
# from google.generativeai.types import HarmCategory, HarmBlockThreshold # Optional, only if using specific safety settings types

# Initialize extensions without binding them to an app yet
db = SQLAlchemy()
cors = CORS()

def create_app():
    """
    Factory function to create the Flask application instance.
    """
    app = Flask(__name__)

    # Load environment variables from .env file
    load_dotenv()

    # Configure the application
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///financial_assistant.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'a-very-secret-key-that-should-be-changed')
    # API configurations stored in app.config
    app.config['EXCHANGE_RATE_API_KEY'] = os.getenv('EXCHANGE_RATE_API_KEY', 'your-exchange-rate-api-key')
    app.config['EXCHANGE_RATE_API_URL'] = "https://v6.exchangerate-api.com/v6/"
    app.config['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY', 'your-gemini-api-key')


    # Initialize extensions with the app instance
    db.init_app(app)
    # Configure CORS - allow requests from any origin
    cors.init_app(app)

    # Configure logging
    # Using basicConfig is often sufficient for development/simple apps
    # For production, consider more advanced logging configurations
    logging.basicConfig(
        filename='app.log',
        level=logging.INFO, # Set this to DEBUG for more verbose output during development
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s' # Added logger name
    )
    # Log configuration status
    if not app.config['EXCHANGE_RATE_API_KEY'] or app.config['EXCHANGE_RATE_API_KEY'] == 'your-exchange-rate-api-key':
         logging.warning("EXCHANGE_RATE_API_KEY is missing or is a placeholder. Exchange rate functionality will be impaired.")
         app.config['EXCHANGE_RATE_API_ENABLED'] = False
    else:
         app.config['EXCHANGE_RATE_API_ENABLED'] = True

    if not app.config['GEMINI_API_KEY'] or app.config['GEMINI_API_KEY'] == 'your-gemini-api-key':
         logging.error("GEMINI_API_KEY is missing or is a placeholder. AI features will be disabled.")
         app.config['AI_ENABLED'] = False
    else:
         try:
            genai.configure(api_key=app.config['GEMINI_API_KEY'])
            app.config['AI_ENABLED'] = True
         except Exception as e:
            logging.error(f"Failed to configure Google Generative AI: {e}. AI features disabled.", exc_info=True)
            app.config['AI_ENABLED'] = False


    # Import models so that SQLAlchemy knows about them when creating tables
    from . import models

    # Import and register blueprints for routes
    from .routes import register_routes
    register_routes(app)

    # Note: db.create_all() is called in run.py within the app_context
    # If you prefer calling it here, uncomment the following block:
    # with app.app_context():
    #     db.create_all()


    logging.info("Flask app created and configured.")
    return app

# The 'db' instance is defined here so it can be imported by models.py and services.py
# The actual app initialization happens inside create_app() via db.init_app()