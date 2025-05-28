from flask import Blueprint, jsonify, request, render_template, send_file
from app.services.financial_service import FinancialService
from app.models.transaction import Transaction
from app import db
import logging
import os
import io
import csv
from datetime import datetime

financial_bp = Blueprint('financial', __name__)

@financial_bp.route('/')
def dashboard_view():
    user_id = 1  # For now, hardcoded user_id
    try:
        all_time_start = "1900-01-01"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        financial_service = FinancialService(
            os.getenv('EXCHANGE_RATE_API_KEY'),
            os.getenv('EXCHANGE_RATE_API_URL', 'https://v6.exchangerate-api.com/v6/')
        )
        
        # Get total income and expenses
        total_income_val = financial_service.get_total_by_type(user_id, 'income', all_time_start, today_str, 'USD')
        total_expenses_val = financial_service.get_total_by_type(user_id, 'expense', all_time_start, today_str, 'USD')
        
        # Handle the values properly for display
        if isinstance(total_income_val, (int, float)):
            display_income = f"{float(total_income_val):.2f}"
        else:
            display_income = "0.00"
            logging.warning(f"Invalid income value received: {total_income_val}")
            
        if isinstance(total_expenses_val, (int, float)):
            display_expenses = f"{float(total_expenses_val):.2f}"
        else:
            display_expenses = "0.00"
            logging.warning(f"Invalid expenses value received: {total_expenses_val}")
        
        # Calculate net balance
        try:
            net_balance = f"{float(display_income) - float(display_expenses):.2f}"
        except ValueError:
            net_balance = "0.00"
            logging.warning("Could not calculate net balance due to invalid values")
        
        # Get recent transactions
        recent_transactions_raw = Transaction.query.filter_by(user_id=user_id)\
            .order_by(Transaction.date.desc())\
            .limit(5)\
            .all()
            
        recent_transactions = [
            {
                "date": tx.date.strftime('%Y-%m-%d'),
                "type": tx.type.capitalize(),
                "description": tx.description,
                "amount": f"{tx.amount:.2f} {tx.currency}"
            } for tx in recent_transactions_raw
        ]
        
        return render_template(
            'dashboard.html',
            total_income=display_income,
            total_expenses=display_expenses,
            net_balance=net_balance,
            recent_transactions=recent_transactions,
            summary_currency="USD"
        )
    except Exception as e:
        logging.error(f"Error in dashboard route: {str(e)}", exc_info=True)
        return render_template(
            'dashboard.html',
            error_message="Could not load dashboard data.",
            total_income="0.00",
            total_expenses="0.00",
            net_balance="0.00",
            recent_transactions=[],
            summary_currency="USD"
        )

@financial_bp.route('/reports/csv')
def download_csv():
    user_id = 1  # For now, hardcoded user_id
    output_filename = f"financial_transactions_user_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    
    transactions = Transaction.query.filter_by(user_id=user_id)\
        .order_by(Transaction.date.desc())\
        .all()
        
    if not transactions:
        return jsonify({"message": "No transactions found for this user to export."}), 404
        
    string_io_buffer = io.StringIO()
    try:
        fieldnames = ['Date', 'Type', 'Amount', 'Currency', 'Category', 'Description']
        writer = csv.DictWriter(string_io_buffer, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        
        for tx in transactions:
            writer.writerow({
                'Date': tx.date.strftime('%Y-%m-%d'),
                'Type': tx.type.capitalize(),
                'Amount': tx.amount,
                'Currency': tx.currency,
                'Category': tx.category,
                'Description': tx.description
            })
            
        csv_data_str = string_io_buffer.getvalue()
        bytes_io_buffer = io.BytesIO(csv_data_str.encode('utf-8'))
        bytes_io_buffer.seek(0)
        
        return send_file(
            bytes_io_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=output_filename
        )
    except Exception as e:
        logging.error(f"Error generating or sending CSV: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to generate CSV report due to an internal error."}), 500
    finally:
        if string_io_buffer:
            string_io_buffer.close() 