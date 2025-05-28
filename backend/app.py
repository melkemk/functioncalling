from flask import Flask, render_template, request, jsonify, send_file, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import requests
import google.generativeai as genai
# from google.generativeai.types import HarmCategory, HarmBlockThreshold # For safety settings
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import csv
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging
import io
import google.api_core.exceptions
from handleapi import x 

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app) # Enable CORS for all routes
app.config['SQLALCHEMY_DATABASE_URI'] =  'sqlite:///financial_assistant.db' 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API credentials
EXCHANGE_RATE_API_URL = "https://v6.exchangerate-api.com/v6/"
EXCHANGE_RATE_API_KEY = os.getenv('EXCHANGE_RATE_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY not found in environment variables. AI features will be disabled.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

if not EXCHANGE_RATE_API_KEY:
    logging.warning("EXCHANGE_RATE_API_KEY not found. Exchange rate functionality will be impaired.")

# Database Models (ensure these are defined as before)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    category = db.Column(db.String(50))
    type = db.Column(db.String(10), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(200))

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# API Integration Functions (ensure these are defined as before)
def get_exchange_rate(from_currency: str, to_currency: str) -> float | str:
    if not EXCHANGE_RATE_API_KEY or EXCHANGE_RATE_API_KEY == 'your-exchange-rate-api-key':
        logging.warning("Exchange rate API key is not configured or is a placeholder.")
        return "Exchange rate service is not available due to missing API key."
    try:
        url = f"{EXCHANGE_RATE_API_URL}{EXCHANGE_RATE_API_KEY}/pair/{from_currency.upper()}/{to_currency.upper()}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('result') == 'success':
            return data['conversion_rate']
        else:
            error_type = data.get('error-type', 'Unknown error')
            logging.error(f"Exchange rate API responded with an error: {error_type}")
            if error_type == 'unknown-code':
                return f"One or both currency codes ('{from_currency}', '{to_currency}') are invalid or not supported by the service."
            return f"Could not fetch exchange rate: {error_type}"
    except requests.Timeout:
        logging.error("Exchange rate API request timed out.")
        return "Exchange rate service timed out. Please try again."
    except requests.RequestException as e:
        logging.error(f"Exchange rate API error: {str(e)}")
        if e.response is not None and e.response.status_code == 404:
            return f"One or both currency codes ('{from_currency}', '{to_currency}') are invalid."
        return f"Error fetching exchange rate: {str(e)}"

def get_current_datetime() -> dict:
    """
    Get the current date and time using datetime.now().
    Returns a dictionary with date and time information.
    """
    try:
        dt = datetime.now()
        return {
            'date': dt.strftime('%Y-%m-%d'),
            'time': dt.strftime('%H:%M'),
            'day_name': dt.strftime('%A'),
            'timezone': 'Local'
        }
    except Exception as e:
        logging.error(f"Error getting current time: {str(e)}")
        return {"error": f"Error getting current time: {str(e)}"}

def add_transaction(user_id: int, amount: float, currency: str, category: str, type: str, description: str, date: str = None, time: str = None) -> str:
    try:
        # Get current datetime if no date/time provided
        current_datetime = datetime.now()
        #the user that a download link will be available.
        
        # Parse date if provided
        if date:
            try:
                transaction_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return "Invalid date format. Please use YYYY-MM-DD."
        else:
            transaction_date = current_datetime.date()
            
        # Parse time if provided
        if time:
            try:
                transaction_time = datetime.strptime(time, "%H:%M").time()
            except ValueError:
                return "Invalid time format. Please use HH:MM."
        else:
            transaction_time = current_datetime.time()
            
        # Combine date and time
        transaction_datetime = datetime.combine(transaction_date, transaction_time)
        
        if type.lower() not in ['income', 'expense']:
            return "Invalid transaction type. Must be 'income' or 'expense'."
            
        if not currency or len(currency) != 3:
            return "Invalid currency code. Must be a 3-letter code (e.g., USD)."
            
        transaction = Transaction(
            user_id=user_id,
            amount=float(amount),
            currency=currency.upper(),
            category=category,
            type=type.lower(),
            description=description,
            date=transaction_datetime
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Format the response with date and time
        formatted_datetime = transaction_datetime.strftime("%Y-%m-%d %H:%M")
        return f"{type.capitalize()} of {amount} {currency.upper()} for '{description}' added successfully at {formatted_datetime}."
        
    except Exception as e:
        logging.error(f"Database error in add_transaction: {str(e)}")
        db.session.rollback()
        return f"Failed to add transaction: {str(e)}"

def get_total_by_type(user_id: int, transaction_type: str, start_date: str, end_date: str, target_currency: str = 'USD') -> float | str:
    try:
        start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return "Invalid date format. Please use YYYY-MM-DD for start and end dates."
    
    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.type == transaction_type.lower(),
        Transaction.date >= start_date_dt,
        Transaction.date < end_date_dt
    ).all()
    
    if not transactions:
        return 0.0
        
    total_in_target_currency = 0.0
    target_currency = target_currency.upper()
    
    for tx in transactions:
        if tx.currency.upper() == target_currency:
            total_in_target_currency += tx.amount
        else:
            rate = get_exchange_rate(tx.currency, target_currency)
            if isinstance(rate, float) and rate > 0:
                total_in_target_currency += tx.amount * rate
            else:
                logging.warning(f"Could not convert {tx.amount} {tx.currency} to {target_currency}. Rate/Error: {rate}")
                error_detail = f" (Exchange service message: {rate})" if isinstance(rate, str) else ""
                return f"Could not calculate total in {target_currency} because conversion for {tx.currency} failed.{error_detail}"
    
    return total_in_target_currency

def generate_pdf_report(user_id: int) -> str:
    try:
        user = User.query.get(user_id)
        report_title_user = f"User {user_id}"
        if user:
            report_title_user = user.username
        
        filename = f"financial_report_{report_title_user.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        logging.info(f"Starting PDF generation for user {user_id} with filename: {filename}")
        
        # Create PDF
        c = canvas.Canvas(filename, pagesize=letter)
        width, height = letter
        
        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawString(72, height - 72, f"Financial Report for {report_title_user}")
        
        # Generation timestamp
        c.setFont("Helvetica", 10)
        c.drawString(72, height - 90, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.line(72, height - 100, width - 72, height - 100)
        
        # Financial Summary
        y_position = height - 130
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y_position, "Financial Summary (approximated in USD)")
        y_position -= 20
        
        # Get financial data
        all_time_start_str = "1900-01-01"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        logging.info(f"Fetching financial data for period {all_time_start_str} to {today_str}")
        total_income_usd = get_total_by_type(user_id, 'income', all_time_start_str, today_str, 'USD')
        total_expense_usd = get_total_by_type(user_id, 'expense', all_time_start_str, today_str, 'USD')
        
        # Format and display financial data
        c.setFont("Helvetica", 11)
        
        # Income
        if isinstance(total_income_usd, (int, float)):
            income_str = f"{total_income_usd:.2f} USD"
        else:
            income_str = f"Error: {total_income_usd}"
            logging.error(f"Invalid income value: {total_income_usd}")
        c.drawString(72, y_position, f"Total Income (all time, in USD): {income_str}")
        y_position -= 18
        
        # Expenses
        if isinstance(total_expense_usd, (int, float)):
            expense_str = f"{total_expense_usd:.2f} USD"
        else:
            expense_str = f"Error: {total_expense_usd}"
            logging.error(f"Invalid expense value: {total_expense_usd}")
        c.drawString(72, y_position, f"Total Expenses (all time, in USD): {expense_str}")
        y_position -= 18
        
        # Net Balance
        if isinstance(total_income_usd, (int, float)) and isinstance(total_expense_usd, (int, float)):
            net_balance = total_income_usd - total_expense_usd
            net_balance_str = f"{net_balance:.2f} USD"
        else:
            net_balance_str = "N/A (calculation error)"
            logging.error("Could not calculate net balance due to invalid income/expense values")
        c.drawString(72, y_position, f"Net Balance (all time, in USD): {net_balance_str}")
        y_position -= 30
        
        # Recent Transactions
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y_position, "Recent Transactions (Last 10)")
        y_position -= 20
        
        transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).limit(10).all()
        logging.info(f"Found {len(transactions)} recent transactions for user {user_id}")
        
        c.setFont("Helvetica", 9)
        if not transactions:
            c.drawString(72, y_position, "No transactions found.")
        else:
            for tx in transactions:
                if y_position < 100:  # Check if we need a new page
                    c.showPage()
                    c.setFont("Helvetica", 9)
                    y_position = height - 72
                
                tx_line = f"{tx.date.strftime('%Y-%m-%d')} | {tx.type.capitalize():<7} | {tx.amount:>8.2f} {tx.currency:<3} | {tx.category:<15} | {tx.description}"
                c.drawString(72, y_position, tx_line)
                y_position -= 14
        
        # Save the PDF
        c.save()
        logging.info(f"Successfully generated PDF report: {filename}")
        return filename
        
    except Exception as e:
        logging.error(f"Error generating PDF report: {str(e)}", exc_info=True)
        raise  # Re-raise the exception to be handled by the route

# Tool declarations (ensure these are defined as before)
TOOL_DECLARATIONS = [
    {'name': 'get_exchange_rate', 'description': 'Get the current exchange rate between two currencies (e.g., USD to EUR). Uses 3-letter currency codes.', 'parameters': {'type': 'object', 'properties': {'from_currency': {'type': 'string', 'description': 'The 3-letter currency code to convert from (e.g., USD). Must be uppercase.'}, 'to_currency': {'type': 'string', 'description': 'The 3-letter currency code to convert to (e.g., EUR). Must be uppercase.'}}, 'required': ['from_currency', 'to_currency']}},
    {'name': 'add_transaction', 'description': 'Add a new financial transaction (income or expense) to the records. Date and time are optional (defaults to now). Date format: YYYY-MM-DD, Time format: HH:MM.', 'parameters': {'type': 'object', 'properties': {'amount': {'type': 'number', 'description': 'The amount of the transaction.'}, 'currency': {'type': 'string', 'description': 'The 3-letter currency code of the transaction (e.g., USD, ETB). Must be uppercase.'}, 'category': {'type': 'string', 'description': 'Category of the transaction (e.g., Salary, Groceries, Utilities).'}, 'type': {'type': 'string', 'description': "Type of transaction: 'income' or 'expense'."}, 'description': {'type': 'string', 'description': 'A brief description of the transaction.'}, 'date': {'type': 'string', 'description': 'Optional: Date of the transaction in YYYY-MM-DD format. Defaults to current date if not provided.'}, 'time': {'type': 'string', 'description': 'Optional: Time of the transaction in HH:MM format. Defaults to current time if not provided.'}}, 'required': ['amount', 'currency', 'category', 'type', 'description']}},
    {'name': 'get_financial_summary', 'description': 'Calculate total income or expenses for a user within a specified date range and optionally in a target currency (defaults to USD).', 'parameters': {'type': 'object', 'properties': {'transaction_type': {'type': 'string', 'description': "The type of transactions to sum: 'income' or 'expense'."}, 'start_date': {'type': 'string', 'description': 'The start date for the period in YYYY-MM-DD format.'}, 'end_date': {'type': 'string', 'description': 'The end date for the period in YYYY-MM-DD format.'}, 'target_currency': {'type': 'string', 'description': 'Optional: The 3-letter currency code to convert the total to (e.g., ETB, USD). Defaults to USD. Must be uppercase.'}}, 'required': ['transaction_type', 'start_date', 'end_date']}},
    {'name': 'generate_pdf_report', 'description': 'Generate and provide a link to a PDF financial report summarizing transactions and balances. The report currently shows all-time summary in USD and recent transactions.', 'parameters': {'type': 'object', 'properties': {}}},
    {'name': 'get_current_datetime', 'description': 'Get the current date and time information from WorldTimeAPI. Returns date, time, day name, and timezone.', 'parameters': {'type': 'object', 'properties': {}}}
]

# Safety settings - defining them robustly
# It's important these types exist at the path genai.types for your version 0.8.5
# If not, this will fall back to default safety settings.
SAFETY_SETTINGS = {}
try:
    SAFETY_SETTINGS = {
        genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
    }
except AttributeError:
    logging.warning("Could not set custom safety settings due to AttributeError (HarmCategory/HarmBlockThreshold not found at genai.types). Using default safety settings.")

def handle_ai_query(user_id: int, query_text: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-api-key':
        logging.warning("Gemini API key is not configured or is a placeholder.")
        return "AI Assistant is not available: API key not configured."
    try:
        # Initialize Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Create the model with proper configuration
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash-latest',
            generation_config={
                'temperature': 0.7,
                'top_p': 0.8,
                'top_k': 40,
            }
        )
        
        # Get chat history for context
        history = ChatHistory.query.filter_by(user_id=user_id)\
            .order_by(ChatHistory.timestamp.desc())\
            .limit(5)\
            .all()
        
        # Build conversation context
        context = "\n".join([f"User: {h.message}\nAssistant: {h.response}" for h in reversed(history)])
        
        # Process transaction commands with more flexible rules
        if any(keyword in query_text.lower() for keyword in ['add income', 'add expense']):
            try:
                # Parse transaction details with more flexible rules
                parts = query_text.lower().split()
                if 'add income' in query_text.lower():
                    amount = float(parts[2])
                    currency = parts[3].upper()
                    category = parts[6] if len(parts) > 6 else 'general'
                    description = ' '.join(parts[8:]) if len(parts) > 8 else category
                    
                    # Create transaction with current date/time if not specified
                    transaction = Transaction(
                        user_id=user_id,
                        amount=amount,
                        currency=currency,
                        category=category,
                        type='income',
                        description=description,
                        date=datetime.utcnow()
                    )
                    db.session.add(transaction)
                    db.session.commit()
                    
                    return f"OK. Income of {amount} {currency} for '{category}' added successfully at {transaction.date.strftime('%Y-%m-%d %H:%M')}."
                    
                elif 'add expense' in query_text.lower():
                    amount = float(parts[2])
                    currency = parts[3].upper()
                    category = parts[6] if len(parts) > 6 else 'general'
                    description = ' '.join(parts[8:]) if len(parts) > 8 else category
                    
                    # Create transaction with current date/time if not specified
                    transaction = Transaction(
                        user_id=user_id,
                        amount=amount,
                        currency=currency,
                        category=category,
                        type='expense',
                        description=description,
                        date=datetime.utcnow()
                    )
                    db.session.add(transaction)
                    db.session.commit()
                    
                    return f"OK. Expense of {amount} {currency} for '{category}' added successfully at {transaction.date.strftime('%Y-%m-%d %H:%M')}."
                    
            except Exception as e:
                db.session.rollback()
                return f"I apologize, but I couldn't process the transaction: {str(e)}"
        
        # For non-transaction queries, use the AI model with context
        chat = model.start_chat(history=[])
        response = chat.send_message(f"{context}\nUser: {query_text}")
        
        if response and response.text:
            return response.text
        else:
            return "I received your message, but I'm not sure how to help with that. Could you please rephrase or ask a specific financial question?"
            
    except Exception as e:
        logging.error(f"General AI Query handling error in handle_ai_query: {str(e)}")
        return f"I apologize, but I encountered an error: {str(e)}"

@app.route('/')
def dashboard_view():
    user_id = 1
    try:
        all_time_start = "1900-01-01"
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Get total income and expenses
        total_income_val = get_total_by_type(user_id, 'income', all_time_start, today_str, 'USD')
        total_expenses_val = get_total_by_type(user_id, 'expense', all_time_start, today_str, 'USD')
        
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
        recent_transactions_raw = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).limit(5).all()
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

@app.route('/chat', methods=['POST'])
def chat():
    user_id = 1
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
        
    user_message = data['message']
    if not user_message.strip():
        return jsonify({'response': "Please type a message to the assistant."})
    
    # Get AI response
    ai_response = handle_ai_query(user_id, user_message)
    
    # Store chat history
    try:
        chat_entry = ChatHistory(
            user_id=user_id,
            message=user_message,
            response=ai_response
        )
        db.session.add(chat_entry)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error storing chat history: {str(e)}")
        # Continue even if history storage fails
    
    return jsonify({'response': ai_response})

@app.route('/chat-history', methods=['GET'])
def get_chat_history():
    user_id = 1
    try:
        # Get the last 50 chat messages
        history = ChatHistory.query.filter_by(user_id=user_id)\
            .order_by(ChatHistory.timestamp.desc())\
            .limit(50)\
            .all()
        
        # Format the history
        formatted_history = [{
            'message': entry.message,
            'response': entry.response,
            'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for entry in reversed(history)]  # Reverse to get chronological order
        
        return jsonify({'history': formatted_history})
    except Exception as e:
        logging.error(f"Error retrieving chat history: {str(e)}")
        return jsonify({'error': 'Could not retrieve chat history'}), 500

@app.route('/chat-page', methods=['GET'])
def chat_page(): return render_template('chat.html')

@app.route('/reports/pdf/<filename>')
def download_pdf_report_file(filename: str):
    try:
        # Security check for filename
        if not (filename.startswith(f"financial_report_user_") or filename.startswith(f"financial_report_demouser_")) or ".." in filename or "/" in filename or "\\" in filename:
            logging.warning(f"Invalid PDF filename attempted: {filename}")
            return jsonify({"error": "Report not found or access denied."}), 404
            
        safe_path = os.path.join(os.getcwd(), filename)
        if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
            logging.warning(f"Attempt to access non-existent PDF report: {filename} at path {safe_path}")
            return jsonify({"error": "Report file not found on server."}), 404
            
        logging.info(f"Sending PDF file: {filename}")
        return send_file(safe_path, as_attachment=True)
        
    except Exception as e:
        error_msg = f"Error sending PDF file {filename}: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return jsonify({"error": "Could not send report file."}), 500

@app.route('/request-pdf-report', methods=['GET'])
def request_pdf_report():
    user_id = 1
    try:
        filename = generate_pdf_report(user_id)
        if not filename:
            raise Exception("PDF generation failed - no filename returned")
            
        # Verify the file exists
        if not os.path.exists(filename):
            raise Exception(f"Generated PDF file not found at path: {filename}")
            
        file_url = url_for('download_pdf_report_file', filename=filename, _external=True)
        logging.info(f"PDF report generated successfully. Download URL: {file_url}")
        
        return jsonify({
            "message": f"PDF report '{filename}' generated successfully.",
            "download_url": file_url,
            "filename": filename
        })
    except Exception as e:
        error_msg = f"Could not generate PDF report: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500

@app.route('/reports/csv')
def download_csv():
    user_id = 1; output_filename = f"financial_transactions_user_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).all()
    if not transactions: return jsonify({"message": "No transactions found for this user to export."}), 404
    string_io_buffer = io.StringIO()
    try:
        fieldnames = ['Date', 'Type', 'Amount', 'Currency', 'Category', 'Description']
        writer = csv.DictWriter(string_io_buffer, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for tx in transactions: writer.writerow({'Date': tx.date.strftime('%Y-%m-%d'), 'Type': tx.type.capitalize(), 'Amount': tx.amount, 'Currency': tx.currency, 'Category': tx.category, 'Description': tx.description})
        csv_data_str = string_io_buffer.getvalue()
        bytes_io_buffer = io.BytesIO(csv_data_str.encode('utf-8')); bytes_io_buffer.seek(0)
        return send_file(bytes_io_buffer, mimetype='text/csv', as_attachment=True, download_name=output_filename)
    except Exception as e: logging.error(f"Error generating or sending CSV: {str(e)}", exc_info=True); return jsonify({"error": "Failed to generate CSV report due to an internal error."}), 500
    finally:
        if string_io_buffer: string_io_buffer.close()

# Main execution and demo data setup 
if __name__ == '__main__':
    with app.app_context():
        if not User.query.first():
            print("Database is empty. Creating a demo user and sample transactions...")
            db.session.add(User(id=1, username='demouser', email='demo@example.com'))
            transactions_data = []
            for tx_data in transactions_data: db.session.add(Transaction(**tx_data))
            db.session.commit()
            print("Demo user and sample transactions created.")
    app.run(debug=True, host='0.0.0.0', port=5000)   