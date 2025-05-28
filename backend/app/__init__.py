from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, 
    template_folder='templates',  # Specify the templates directory
    static_folder='static'        # Specify the static directory
)
CORS(app)

# Configure app
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///financial_assistant.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

# Initialize database
db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Import models first
from app.models.user import User
from app.models.transaction import Transaction
from app.models.chat_history import ChatHistory

# Import and register blueprints
from app.routes.chat_routes import chat_bp
from app.routes.financial_routes import financial_bp

app.register_blueprint(chat_bp)
app.register_blueprint(financial_bp)

# Create database tables
with app.app_context():
    db.create_all()
    
    # Create demo user and transactions if database is empty
    if not User.query.first():
        print("Database is empty. Creating a demo user and sample transactions...")
        db.session.add(User(id=1, username='demouser', email='demo@example.com'))
        
        transactions_data = [
            {'user_id': 1, 'amount': 2500, 'currency': 'USD', 'category': 'Salary', 
             'type': 'income', 'description': 'Monthly Salary', 'date': datetime(2024, 1, 5)},
            {'user_id': 1, 'amount': 150, 'currency': 'USD', 'category': 'Groceries', 
             'type': 'expense', 'description': 'Weekly shopping', 'date': datetime(2024, 1, 7)},
            {'user_id': 1, 'amount': 75, 'currency': 'USD', 'category': 'Utilities', 
             'type': 'expense', 'description': 'Internet Bill', 'date': datetime(2024, 1, 10)},
            {'user_id': 1, 'amount': 50000, 'currency': 'ETB', 'category': 'Freelance', 
             'type': 'income', 'description': 'Project Y - ETB', 'date': datetime(2024, 1, 15)},
            {'user_id': 1, 'amount': 50, 'currency': 'EUR', 'category': 'Software', 
             'type': 'expense', 'description': 'Subscription', 'date': datetime(2024, 1, 20)},
        ]
        
        for tx_data in transactions_data:
            db.session.add(Transaction(**tx_data))
            
        db.session.commit()
        print("Demo user and sample transactions created.") 