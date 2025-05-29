# app/routes/main_routes.py
from flask import render_template, Blueprint
import logging
from datetime import datetime
from ..models import Transaction # Need to import models to query database
from ..services.financial_service import get_total_by_type # Need service to get summary data

# Create a Blueprint named 'main'
main = Blueprint('main', __name__)

@main.route('/')
def dashboard_view():
    """Renders the main dashboard view."""
    user_id = 1 # Assuming a single user for now

    try:
        # Get financial summary data using the service layer
        # For dashboard, show all-time summary in USD
        earliest_tx = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.asc()).first()
        all_time_start_str = earliest_tx.date.strftime('%Y-%m-%d') if earliest_tx else "1900-01-01"
        today_str = datetime.now().strftime("%Y-%m-%d")


        total_income_val = get_total_by_type(user_id, 'income', all_time_start_str, today_str, 'USD')
        total_expenses_val = get_total_by_type(user_id, 'expense', all_time_start_str, today_str, 'USD')

        # Handle service function potentially returning error strings
        if isinstance(total_income_val, (int, float)):
            display_income = f"{float(total_income_val):,.2f}" # Format with commas
        else:
            display_income = "N/A" # Or show error message
            logging.warning(f"Dashboard: Invalid income value received: {total_income_val}")
            # Optionally pass an error message to the template

        if isinstance(total_expenses_val, (int, float)):
            display_expenses = f"{float(total_expenses_val):,.2f}" # Format with commas
        else:
            display_expenses = "N/A" # Or show error message
            logging.warning(f"Dashboard: Invalid expenses value received: {total_expenses_val}")
            # Optionally pass an error message to the template


        # Calculate net balance only if both income and expenses are valid numbers
        try:
            if isinstance(total_income_val, (int, float)) and isinstance(total_expenses_val, (int, float)):
                 net_balance = f"{total_income_val - total_expenses_val:,.2f}" # Format with commas
            else:
                 net_balance = "N/A"
        except ValueError:
            net_balance = "N/A"
            logging.warning("Dashboard: Could not calculate net balance due to invalid values")

        # Get recent transactions directly from the database model
        recent_transactions_raw = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).limit(5).all()
        recent_transactions = [
            {
                "date": tx.date.strftime('%Y-%m-%d %H:%M'), # Include time
                "type": tx.type.capitalize(),
                "description": tx.description,
                "category": tx.category or 'N/A', # Handle None
                "amount": f"{tx.amount:,.2f} {tx.currency.upper()}" # Format amount
            } for tx in recent_transactions_raw
        ]

        # Pass data to the template
        return render_template(
            'dashboard.html',
            total_income=display_income,
            total_expenses=display_expenses,
            net_balance=net_balance,
            recent_transactions=recent_transactions,
            summary_currency="USD" # Indicate the currency for the summary
        )

    except Exception as e:
        logging.error(f"Error loading dashboard for user {user_id}: {str(e)}", exc_info=True)
        # Render template with error message or default values
        return render_template(
            'dashboard.html',
            error_message="Could not load dashboard data due to an error.",
            total_income="N/A",
            total_expenses="N/A",
            net_balance="N/A",
            recent_transactions=[],
            summary_currency="USD" # Still indicate intended currency
        )


@main.route('/chat-page', methods=['GET'])
def chat_page():
    """Renders the chat page view."""
    return render_template('chat.html')