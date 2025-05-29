# app/services/financial_service.py
from .. import db # Import the db instance
from ..models import Transaction, User # Import models
from .exchange_service import get_exchange_rate # Import necessary services
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import csv
import io
import os
import logging

def add_transaction(user_id: int, amount: float, currency: str, category: str, type: str, description: str, date: str = None, time: str = None) -> str:
    """Adds a new financial transaction to the database."""
    try:
        # Get current datetime if no date/time provided for defaults
        current_datetime = datetime.now()

        # Parse date if provided
        if date:
            try:
                # Ensure date is just the date part for combining
                transaction_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                return "Invalid date format. Please use YYYY-MM-DD."
        else:
            transaction_date = current_datetime.date()

        # Parse time if provided
        if time:
            try:
                # Ensure time is just the time part for combining
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

        # Ensure amount is positive; type dictates if it's added or subtracted later
        amount = abs(float(amount))

        transaction = Transaction(
            user_id=user_id,
            amount=amount, # Store as positive
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
        return f"{type.capitalize()} of {amount:.2f} {currency.upper()} for '{description}' added successfully at {formatted_datetime}."

    except Exception as e:
        logging.error(f"Database error in add_transaction for user {user_id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return f"Failed to add transaction: {str(e)}"


def get_total_by_type(user_id: int, transaction_type: str, start_date: str, end_date: str, target_currency: str = 'USD') -> float | str:
    """Calculates the total amount for a given transaction type and date range, converted to a target currency."""
    try:
        # Parse dates
        start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # For inclusivity, we want to include the entire end date
        # So we add one day to end_date_dt and use < instead of <=
        end_date_dt = end_date_dt + timedelta(days=1)
        
        logging.info(f"Calculating {transaction_type} from {start_date} to {end_date} (inclusive) for user {user_id}")
        
        transactions = Transaction.query.filter(
            Transaction.user_id == user_id,
            Transaction.type == transaction_type.lower(),
            Transaction.date >= start_date_dt,
            Transaction.date < end_date_dt  # Using < with end_date_dt + 1 day to include the entire end date
        ).all()

        if not transactions:
            logging.info(f"No {transaction_type} transactions found for user {user_id} in the specified date range")
            return 0.0

        total_in_target_currency = 0.0
        target_currency = target_currency.upper()

        for tx in transactions:
            if tx.currency.upper() == target_currency:
                total_in_target_currency += tx.amount
            else:
                # Use the imported exchange rate service
                rate = get_exchange_rate(tx.currency, target_currency)
                if isinstance(rate, float) and rate > 0:
                    total_in_target_currency += tx.amount * rate
                else:
                    logging.warning(f"Could not convert {tx.amount} {tx.currency} to {target_currency} for user {user_id}. Exchange rate service returned: {rate}")
                    error_detail = f" (Exchange service message: {rate})" if isinstance(rate, str) else ""
                    return f"Could not calculate total in {target_currency} because conversion for {tx.currency} failed.{error_detail}"

        logging.info(f"Total {transaction_type} for user {user_id}: {total_in_target_currency} {target_currency}")
        return total_in_target_currency

    except ValueError as e:
        logging.error(f"Date parsing error in get_total_by_type for user {user_id}: {str(e)}")
        return "Invalid date format. Please use YYYY-MM-DD for start and end dates."
    except Exception as e:
        logging.error(f"Error in get_total_by_type for user {user_id}: {str(e)}", exc_info=True)
        return f"An error occurred while calculating the total: {str(e)}"


def generate_pdf_report(user_id: int) -> str:
    """Generates a PDF financial report for the user and returns the filename."""
    try:
        user = User.query.get(user_id)
        report_title_user = f"User {user_id}"
        if user:
            report_title_user = user.username

        # Define where reports are saved - default to current working directory or a specific folder
        # report_dir = "reports"
        # os.makedirs(report_dir, exist_ok=True) # Ensure directory exists
        # filename = os.path.join(report_dir, f"financial_report_{report_title_user.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
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

        # Financial Summary (All Time)
        y_position = height - 130
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, y_position, "Financial Summary (approximated in USD - All Time)")
        y_position -= 20

        # Get financial data
        # Find the earliest transaction date for a true "all time" report
        earliest_tx = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.asc()).first()
        all_time_start_str = earliest_tx.date.strftime('%Y-%m-%d') if earliest_tx else "1900-01-01" # Use a very early date if no transactions
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
            logging.error(f"Invalid income value for user {user_id}: {total_income_usd}")
        c.drawString(72, y_position, f"Total Income: {income_str}")
        y_position -= 18

        # Expenses
        if isinstance(total_expense_usd, (int, float)):
            expense_str = f"{total_expense_usd:.2f} USD"
        else:
            expense_str = f"Error: {total_expense_usd}"
            logging.error(f"Invalid expense value for user {user_id}: {total_expense_usd}")
        c.drawString(72, y_position, f"Total Expenses: {expense_str}")
        y_position -= 18

        # Net Balance
        if isinstance(total_income_usd, (int, float)) and isinstance(total_expense_usd, (int, float)):
            net_balance = total_income_usd - total_expense_usd
            net_balance_str = f"{net_balance:.2f} USD"
        else:
            net_balance_str = "N/A (calculation error)"
            logging.error(f"Could not calculate net balance for user {user_id} due to invalid income/expense values")
        c.drawString(72, y_position, f"Net Balance: {net_balance_str}")
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
            # Draw table headers (optional but nice)
            header_y = y_position
            c.setFont("Helvetica-Bold", 9)
            c.drawString(72, header_y, "Date")
            c.drawString(140, header_y, "Type")
            c.drawString(190, header_y, "Amount")
            c.drawString(260, header_y, "Currency")
            c.drawString(320, header_y, "Category")
            c.drawString(420, header_y, "Description")
            c.line(72, header_y - 2, width - 72, header_y - 2)
            y_position -= 14 # Space after headers

            c.setFont("Helvetica", 9) # Back to regular font for data
            for tx in transactions:
                if y_position < 100:  # Check if we need a new page
                    c.showPage()
                    c.setFont("Helvetica", 9)
                    y_position = height - 72
                    # Repeat headers on new page (optional)
                    c.setFont("Helvetica-Bold", 9)
                    c.drawString(72, y_position, "Date")
                    c.drawString(140, y_position, "Type")
                    c.drawString(190, y_position, "Amount")
                    c.drawString(260, y_position, "Currency")
                    c.drawString(320, y_position, "Category")
                    c.drawString(420, y_position, "Description")
                    c.line(72, y_position - 2, width - 72, y_position - 2)
                    y_position -= 14
                    c.setFont("Helvetica", 9) # Back to regular font

                # Format amount to 2 decimal places
                amount_str = f"{tx.amount:.2f}"

                c.drawString(72, y_position, tx.date.strftime('%Y-%m-%d %H:%M'))
                c.drawString(140, y_position, tx.type.capitalize())
                c.drawString(190, y_position, amount_str)
                c.drawString(260, y_position, tx.currency.upper())
                c.drawString(320, y_position, tx.category or 'N/A') # Handle potentially None category
                c.drawString(420, y_position, tx.description or 'N/A') # Handle potentially None description
                y_position -= 14 # Space between rows


        # Save the PDF
        c.save()
        logging.info(f"Successfully generated PDF report: {filename} for user {user_id}")
        return filename # Return the filename

    except Exception as e:
        logging.error(f"Error generating PDF report for user {user_id}: {str(e)}", exc_info=True)
        # Re-raise the exception so the route knows it failed and can return an error response
        raise


def generate_csv_data(user_id: int) -> io.BytesIO | None:
    """Generates CSV data for all transactions for a user and returns it as a BytesIO buffer."""
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.date.desc()).all()

    if not transactions:
        return None # Indicate no data found

    # Use StringIO first as csv module works with strings
    string_io_buffer = io.StringIO()

    try:
        fieldnames = ['Date', 'Time', 'Type', 'Amount', 'Currency', 'Category', 'Description']
        writer = csv.DictWriter(string_io_buffer, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)

        writer.writeheader()

        for tx in transactions:
            writer.writerow({
                'Date': tx.date.strftime('%Y-%m-%d'),
                'Time': tx.date.strftime('%H:%M'),
                'Type': tx.type.capitalize(),
                'Amount': tx.amount,
                'Currency': tx.currency.upper(),
                'Category': tx.category or '', # Use empty string for None category in CSV
                'Description': tx.description or '' # Use empty string for None description in CSV
            })

        # Get the string content and encode it to bytes
        csv_data_str = string_io_buffer.getvalue()
        bytes_io_buffer = io.BytesIO(csv_data_str.encode('utf-8'))
        bytes_io_buffer.seek(0) # Rewind to the beginning of the buffer

        return bytes_io_buffer # Return the BytesIO buffer

    except Exception as e:
        logging.error(f"Error generating CSV data for user {user_id}: {str(e)}", exc_info=True)
        raise # Re-raise the exception

    finally:
        # Ensure the StringIO buffer is closed
        if string_io_buffer:
            string_io_buffer.close()