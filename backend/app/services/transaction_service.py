from datetime import datetime, timedelta
import logging
from app.models.models import Transaction
from app.services.exchange_service import ExchangeRateService
from app import db

class TransactionService:
    """Service for handling financial transaction operations."""
    
    @staticmethod
    def add_transaction(user_id: int, amount: float, currency: str, category: str, 
                       type: str, description: str, date: str = None, time: str = None) -> str:
        """
        Add a new financial transaction.
        
        Args:
            user_id (int): The ID of the user
            amount (float): The transaction amount
            currency (str): The 3-letter currency code
            category (str): The transaction category
            type (str): The transaction type ('income' or 'expense')
            description (str): The transaction description
            date (str, optional): The transaction date in YYYY-MM-DD format
            time (str, optional): The transaction time in HH:MM format
            
        Returns:
            str: Success message or error message
        """
        try:
            # Get current datetime if no date/time provided
            current_datetime = datetime.now()
            
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
    
    @staticmethod
    def get_total_by_type(user_id: int, transaction_type: str, start_date: str, 
                         end_date: str, target_currency: str = 'USD') -> float | str:
        """
        Calculate total income or expenses for a user within a date range.
        
        Args:
            user_id (int): The ID of the user
            transaction_type (str): The type of transactions to sum ('income' or 'expense')
            start_date (str): The start date in YYYY-MM-DD format
            end_date (str): The end date in YYYY-MM-DD format
            target_currency (str, optional): The currency to convert totals to. Defaults to 'USD'.
            
        Returns:
            float | str: The total amount if successful, error message if failed
        """
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
                rate = ExchangeRateService.get_exchange_rate(tx.currency, target_currency)
                if isinstance(rate, float) and rate > 0:
                    total_in_target_currency += tx.amount * rate
                else:
                    logging.warning(f"Could not convert {tx.amount} {tx.currency} to {target_currency}. Rate/Error: {rate}")
                    error_detail = f" (Exchange service message: {rate})" if isinstance(rate, str) else ""
                    return f"Could not calculate total in {target_currency} because conversion for {tx.currency} failed.{error_detail}"
        
        return total_in_target_currency 