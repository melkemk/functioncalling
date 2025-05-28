from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from app.config.config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS, SECRET_KEY
import logging

# Initialize SQLAlchemy
db = SQLAlchemy()

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Configure the app
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS
    app.config['SECRET_KEY'] = SECRET_KEY
    
    # Initialize extensions
    db.init_app(app)
    
    # Register blueprints
    from app.routes.chat_routes import chat_bp
    from app.routes.transaction_routes import transaction_bp
    
    app.register_blueprint(chat_bp, url_prefix='/api')
    app.register_blueprint(transaction_bp, url_prefix='/api')
    
    # Add root route
    @app.route('/')
    def index():
        return jsonify({
            'status': 'ok',
            'message': 'Financial Assistant API is running',
            'endpoints': {
                'chat': '/api/chat',
                'chat_history': '/api/chat/history',
                'transaction': '/api/transaction',
                'transaction_summary': '/api/transaction/summary',
                'transaction_breakdown': '/api/transaction/breakdown',
                'transaction_trends': '/api/transaction/trends'
            }
        })
    
    # Create database tables
    with app.app_context():
        try:
            db.create_all()
            logging.info("Database tables created successfully")
        except Exception as e:
            logging.error(f"Error creating database tables: {str(e)}")
            raise
    
    return app 