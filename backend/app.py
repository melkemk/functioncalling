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


# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app) # Enable CORS for all routes
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///financial_assistant.db')
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

# [Previous code from your script remains unchanged up to the handle_ai_query function]
# ... (User, Transaction, ChatHistory models, db setup, API integration functions, TOOL_DECLARATIONS, SAFETY_SETTINGS etc.)

def handle_ai_query(user_id: int, query_text: str) -> str:
    if not GEMINI_API_KEY or GEMINI_API_KEY == 'your-gemini-api-key':
        logging.warning("Gemini API key is not configured or is a placeholder.")
        return "AI Assistant is not available: API key not configured."
    try:
        model_init_args = {
            'model_name': 'gemini-1.5-flash-latest',
            'system_instruction': (
                "You are a precise, proactive, and highly autonomous financial assistant. "
                "Your primary role is to help users manage and understand their finances by intelligently calling the available tools. "
                "You MUST proactively interpret user queries to extract necessary parameters for tool calls. "

                "TOOL CALLING - GENERAL RULES: "
                "For each tool, its description specifies 'required' parameters. You MUST ensure all required parameters have values before calling the tool. "
                "  - If the user's query provides a value, use it. "
                "  - If a value can be reasonably and confidently inferred (e.g., 'dollars' implies 'USD' for currency, 'today' for a date if unspecified for a new transaction), infer it. "
                "  - If a required parameter's value is missing from the user's query and cannot be confidently inferred (e.g., 'category' or 'description' for `add_transaction` if the user only says 'add 100 income'), you MUST explicitly ask the user for that specific missing information. Example: 'Okay, I can add that income. What category should I put it under, and do you have a short description for it?'"
                "DO NOT call a tool if its required parameters are still missing after your inference and you haven't asked the user. "
                "DO NOT ask clarifying questions for information that *can* be reasonably inferred or is listed as optional and not provided. "


                "CRITICAL INSTRUCTION FOR DATE AND TIME QUERIES (USER FACING): "
                "When users ask about the current date, time, or day of the week, ALWAYS use the get_current_datetime() function. "
                "This function provides accurate current date and time information. "
                "Examples of when to use it: "
                "  - User: 'what day is it?' -> Call get_current_datetime() "
                "  - User: 'what's today's date?' -> Call get_current_datetime() "
                "  - User: 'what time is it?' -> Call get_current_datetime() "
                "Present this information in a friendly, natural way to the user. "

                "CRITICAL INSTRUCTION FOR CURRENCY CODES (Exchange Rates & Transactions): "
                "When a user query involves country names, specific currencies by name, or common currency understanding (e.g., 'dollars' usually means USD, 'pounds' usually GBP, 'euro' is EUR), "
                "you MUST independently identify and use the correct 3-letter ISO currency codes (e.g., USD, ETB, KES, EUR, GBP, JPY, CNY, INR, CAD, AUD). ALWAYS use UPPERCASE for currency codes when calling tools. "
                "DO NOT ask the user for these codes if the country or currency name is given or clearly implied. "
                "Examples of your inference: "
                "  - User: 'exchange rate Ethiopia to USA' -> Call `get_exchange_rate` with `from_currency='ETB'`, `to_currency='USD'`. "
                "  - User: 'add income of 1000 Ethiopian birr' -> Call `add_transaction` with `currency='ETB'`. "

                "DATE AND TIME HANDLING (Transactions & Summaries): "
                "Tool functions require dates in YYYY-MM-DD format and times in HH:MM format. "
                "You MUST autonomously convert all natural language date and time references into these precise formats. Do not ask the user for reformatting if your inference is sound. "

                "General Natural Language Dates: For terms like 'today', 'yesterday', 'last Tuesday', 'next Monday', 'tomorrow', specific dates like 'January 5th' or 'May 10 2023', you must calculate the exact YYYY-MM-DD date. If a year isn't specified for a date like 'March 15th', assume the current year unless context implies otherwise (e.g., 'last March 15th' would refer to the previous year's March 15th). "

                "Specific Instructions for `get_financial_summary` Date Ranges: "
                "  - For queries about 'all time' totals (e.g., 'what is my total income ever?'): "
                "    If the user asks for an 'all time' summary without specifying a start date, ask them for a practical start year or month/year for their records (e.g., 'To calculate your all-time income, could you please provide a start year for your records, like 2000?'). Avoid using extremely old default dates like '1900-01-01' yourself, as it might cause errors. If they provide a start like 'since 2000', use '2000-01-01' as start_date and the current date as end_date. "
                "  - For a single month query (e.g., 'income in January 2023', 'summary for Feb 2024'): "
                "    The `start_date` is the first day of that month (e.g., '2023-01-01' for 'January 2023'). "
                "    The `end_date` is the *last day* of that month (e.g., '2023-01-31' for 'January 2023', '2024-02-29' for 'Feb 2024'). You must correctly determine the last day, accounting for leap years. "
                "  - For a range like 'Month1 Year1 to Month2 Year2' (e.g., 'January 2000 to February 2025'): "
                "    The `start_date` is the first day of Month1 Year1 (e.g., '2000-01-01' for 'January 2000'). "
                "    The `end_date` is the *last day* of Month2 Year2 (e.g., '2025-02-28' for 'February 2025'). You must correctly determine this last day, accounting for leap years. "
                "  - For a range specified only by years (e.g., 'income from 2020 to 2022', 'expenses during 2021-2023', 'what is income from 2000 to 2025'): "
                "    The `start_date` is the first day of the start year (e.g., '2020-01-01' for start year 2020). "
                "    The `end_date` is the *last day* of the end year (e.g., '2022-12-31' for end year 2022). You must correctly determine this last day. "
                "  - If a single year is mentioned for a summary (e.g., 'income in 2021', 'expenses for 2023'): "
                "    The `start_date` is 'YYYY-01-01' and `end_date` is 'YYYY-12-31' for that year. "
                "  - For relative ranges like 'last month', 'this month', 'this year', 'past 30 days': "
                "    Calculate the precise `start_date` and `end_date` (YYYY-MM-DD). You will need to know the current date for these. If needed, use `get_current_datetime` to obtain the current date for these calculations. For example (assuming current date is 2025-05-28): "
                "        - 'last month': `start_date: 2025-04-01`, `end_date: 2025-04-30`. "
                "        - 'this year': `start_date: 2025-01-01`, `end_date: 2025-12-31`. "
                "Always provide both `start_date` and `end_date` in YYYY-MM-DD format to the `get_financial_summary` tool. "

                "Specific Instructions for `add_transaction` Date and Time: "
                "  - If no date is specified by the user, default to today's date (YYYY-MM-DD). Use `get_current_datetime` to obtain this if needed. "
                "  - If no time is specified, default to the current time (HH:MM). Use `get_current_datetime` to obtain this if needed. "
                "  - If natural language like 'yesterday at 3pm' or 'Jan 5th 9am' is used, convert to YYYY-MM-DD and HH:MM. For 'yesterday', calculate based on the current date. "

                "Examples of Date/Time Conversion for `get_financial_summary`: "
                "  - User: 'how much income did I make in March 2023?' -> Call `get_financial_summary` with `start_date='2023-03-01'`, `end_date='2023-03-31'`. "
                "  - User: 'show expenses from 2022 to 2024' -> Call `get_financial_summary` with `start_date='2022-01-01'`, `end_date='2024-12-31'`. "

                "TOOL PARAMETER REQUIREMENTS (reiteration of general rule): "
                "  - `get_exchange_rate`: `from_currency`, `to_currency` (both 3-letter uppercase ISO codes). "
                "  - `add_transaction`: `amount` (number), `currency` (3-letter uppercase), `category` (string), `type` ('income' or 'expense'), `description` (string), `date` (optional YYYY-MM-DD), `time` (optional HH:MM). Remember: `category` and `description` ARE REQUIRED. If not provided or inferable, ASK the user. "
                "  - `get_financial_summary`: `transaction_type` ('income' or 'expense'), `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD), `target_currency` (optional 3-letter uppercase, defaults to USD). "
                "  - `generate_pdf_report`: No parameters. "

                "RESPONSE GUIDELINES: "
                "1. After successfully calling a tool, present the results from the function in a clear, human-readable sentence or summary. Always state currency explicitly. "
                "2. If a tool function returns an error string, explain the error clearly to the user in simple terms. If possible, suggest how they might fix their query or inform them if it's a system issue. "
                "3. For PDF reports, confirm generation: 'I've generated the PDF report...' "
                "4. Be concise. A simple confirmation is often sufficient. "
                "5. (Covered by general tool calling rules) If required information is missing, ask for it. "
                "6. After executing a function and receiving its result, ALWAYS provide a final textual response to the user summarizing the outcome or presenting the data. "
            )
        }
        if SAFETY_SETTINGS: # Pass safety_settings only if it's not an empty dict
            model_init_args['safety_settings'] = SAFETY_SETTINGS
        
        model = genai.GenerativeModel(**model_init_args)

        available_functions = {
            'get_exchange_rate': get_exchange_rate,
            'add_transaction': lambda **args_inner: add_transaction(user_id=user_id, **args_inner),
            'get_financial_summary': lambda **args_inner: get_total_by_type(user_id=user_id, **args_inner),
            'generate_pdf_report': lambda: generate_pdf_report(user_id=user_id),
            'get_current_datetime': get_current_datetime
        }

        chat = model.start_chat(history=[]) # Fresh chat for each query for now
        
        logging.info(f"User {user_id} query to Gemini: {query_text}")
        response = chat.send_message(query_text, tools=[{'function_declarations': TOOL_DECLARATIONS}])
        
        function_call_part_found = None
        if response.parts: 
            for part_item in response.parts:
                if part_item.function_call:
                    function_call_part_found = part_item
                    break
        
        if function_call_part_found:
            fc = function_call_part_found.function_call
            func_name = fc.name
            args = {key: value for key, value in fc.args.items()}
            logging.info(f"Gemini calling function: {func_name} with args: {args}")

            tool_response_payload = {} 
            if func_name in available_functions:
                try:
                    function_result = available_functions[func_name](**args)
                    logging.info(f"Function {func_name} raw result: {function_result}")
                    
                    tool_response_payload = {"result": function_result}
                    if func_name == 'generate_pdf_report': # Ensure this custom payload is still relevant
                        tool_response_payload = {"result": f"PDF report '{function_result}' has been generated."} 
                    
                    # Send tool result back to the model
                    response = chat.send_message(str(tool_response_payload)) # Using str() as per original stable approach

                except Exception as e:
                    logging.error(f"Error executing function {func_name} locally: {str(e)}", exc_info=True)
                    # Inform the model about the error with the tool execution
                    response = chat.send_message(f"An error occurred on my end while trying to use the {func_name} tool: {str(e)}")
            else:
                logging.error(f"Unknown function called by Gemini: {func_name}")
                response = chat.send_message(f"I tried to use a tool named '{func_name}', but it's not one I recognize.")
        
        final_text = ""
        if response and response.parts: 
            for part_item in response.parts:
                if hasattr(part_item, 'text') and part_item.text: 
                    final_text += part_item.text
        
        if not final_text: # Fallback if AI gives no text response
            logging.warning(f"Gemini final response text is empty. Response parts: {response.parts if response else 'No response object'}")
            if function_call_part_found: # If a tool was called
                payload_str = str(tool_response_payload) if 'tool_response_payload' in locals() and tool_response_payload else "Tool executed."
                final_text = f"I've processed your request with the tool: {func_name}. Outcome (raw string): {payload_str}. Any other questions?"
            elif query_text.strip().lower() in ["hey", "hi", "hello", "asdf", "how are you"]: # Simple greetings
                final_text = "Hello! I'm your financial assistant. How can I help you with your finances today?"
            else: # Generic fallback
                final_text = "I received your message, but I'm not sure how to respond. Could you please try rephrasing or ask a specific financial question?"
            
        logging.info(f"Final AI response to user: {final_text}")
        return final_text

    except google.api_core.exceptions.NotFound as e:
        logging.error(f"Model not found or API version issue: {str(e)}", exc_info=True)
        current_model_name = model_init_args.get('model_name', 'the configured model') if 'model_init_args' in locals() else 'the configured model'
        return f"AI Assistant Error: The AI model ('{current_model_name}') was not found or is not supported. Please check model name and API configuration."
    except google.api_core.exceptions.InvalidArgument as e:
        logging.error(f"InvalidArgument error with Gemini API: {str(e)}", exc_info=True)
        return f"AI Assistant Error: Invalid argument sent to the API. Details: {str(e)}"
    except Exception as e:
        logging.error(f"General AI Query handling error in handle_ai_query: {str(e)}", exc_info=True)
        err_str = str(e).lower()
        if "api key" in err_str or "permission_denied" in err_str or "unauthenticated" in err_str:
            return "AI Assistant Error: API key problem or authentication failure. Verify server configuration."
        if "quota" in err_str or "resource_exhausted" in err_str:
            return "AI Assistant Error: API usage quota likely exceeded. Please try again later or check your quota."
        return "An unexpected error occurred while communicating with the AI assistant. Please check logs."

# ... (Flask routes and the rest of your script remain unchanged)
# @app.route('/')
# def dashboard_view():
# ... etc.


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
            transactions_data = [
                {'user_id': 1, 'amount': 2500, 'currency': 'USD', 'category': 'Salary', 'type': 'income', 'description': 'Monthly Salary', 'date': datetime(2024, 1, 5)},
                {'user_id': 1, 'amount': 150, 'currency': 'USD', 'category': 'Groceries', 'type': 'expense', 'description': 'Weekly shopping', 'date': datetime(2024, 1, 7)},
                {'user_id': 1, 'amount': 75, 'currency': 'USD', 'category': 'Utilities', 'type': 'expense', 'description': 'Internet Bill', 'date': datetime(2024, 1, 10)},
                {'user_id': 1, 'amount': 50000, 'currency': 'ETB', 'category': 'Freelance', 'type': 'income', 'description': 'Project Y - ETB', 'date': datetime(2024, 1, 15)},
                {'user_id': 1, 'amount': 50, 'currency': 'EUR', 'category': 'Software', 'type': 'expense', 'description': 'Subscription', 'date': datetime(2024, 1, 20)},
            ]
            for tx_data in transactions_data: db.session.add(Transaction(**tx_data))
            db.session.commit()
            print("Demo user and sample transactions created.")
    app.run(debug=True, host='0.0.0.0', port=5000)  