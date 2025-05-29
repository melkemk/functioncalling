# run.py
import os
from app import create_app
from app import db # Need db instance to create tables and add demo data
from app.models import User, Transaction, ChatHistory # Need models for demo data
from datetime import datetime, timedelta, time

# Create the Flask app using the factory pattern
app = create_app()

if __name__ == '__main__':
    # This block ensures that db.create_all() is called within the app context
    # and also handles the demo data creation.
    with app.app_context():
        db.create_all()

        # Create demo user and data if database is empty
        if not User.query.first():
            print("Database is empty. Creating a demo user and sample transactions...")
            demo_user = User(id=1, username='demouser', email='demo@example.com')
            db.session.add(demo_user)

            # Add some sample transactions (replace with your desired sample data)
            sample_transactions = [
                {'user_id': 1, 'amount': 2500.0, 'currency': 'USD', 'category': 'Salary', 'type': 'income', 'description': 'Monthly paycheck', 'date': datetime.now().replace(day=1)},
                {'user_id': 1, 'amount': 150.0, 'currency': 'USD', 'category': 'Groceries', 'type': 'expense', 'description': 'Weekly shopping at market', 'date': datetime.now() - timedelta(days=3)},
                {'user_id': 1, 'amount': 75.0, 'currency': 'EUR', 'category': 'Eating Out', 'type': 'expense', 'description': 'Dinner with friends', 'date': datetime.now() - timedelta(days=2), 'time': datetime.now().time()},
                {'user_id': 1, 'amount': 500.0, 'currency': 'ETB', 'category': 'Transport', 'type': 'expense', 'description': 'Taxi fares', 'date': datetime.now() - timedelta(days=1)},
                {'user_id': 1, 'amount': 100.0, 'currency': 'USD', 'category': 'Freelance', 'type': 'income', 'description': 'Project payment', 'date': datetime.now() - timedelta(days=7)},
                {'user_id': 1, 'amount': 30.0, 'currency': 'GBP', 'category': 'Subscriptions', 'type': 'expense', 'description': 'Software subscription', 'date': datetime.now().replace(day=15)},
            ]

            for tx_data in sample_transactions:
                # Convert date/time if necessary, or ensure they are datetime objects
                if isinstance(tx_data.get('date'), datetime) and isinstance(tx_data.get('time'), time):
                     tx_datetime = datetime.combine(tx_data['date'].date(), tx_data['time'])
                     del tx_data['time'] # Remove time key before passing to Transaction constructor
                elif isinstance(tx_data.get('date'), datetime):
                     tx_datetime = tx_data['date']
                else:
                     tx_datetime = datetime.utcnow() # Fallback

                tx_data['date'] = tx_datetime # Ensure date is a datetime object

                db.session.add(Transaction(**tx_data))

            db.session.commit()
            print("Demo user and sample transactions created.")

    # Run the Flask development server
    # For production, use a production-ready WSGI server like Gunicorn or uWSGI
    app.run(debug=True, host='0.0.0.0', port=5000)