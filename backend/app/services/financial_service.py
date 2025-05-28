import logging
import requests
from datetime import datetime, timedelta
from app.models.transaction import Transaction
from app import db

class FinancialService:
    def __init__(self, exchange_rate_api_key, exchange_rate_api_url):
        self.exchange_rate_api_key = exchange_rate_api_key
        self.exchange_rate_api_url = exchange_rate_api_url

    def get_exchange_rate(self, from_currency: str, to_currency: str) -> float | str:
        if not self.exchange_rate_api_key:
            logging.warning("Exchange rate API key is not configured.")
            return "Exchange rate service is not available due to missing API key."

        try:
            url = f"{self.exchange_rate_api_url}{self.exchange_rate_api_key}/pair/{from_currency.upper()}/{to_currency.upper()}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('result') == 'success':
                return data['conversion_rate']
            else:
                error_type = data.get('error-type', 'Unknown error')
                logging.error(f"Exchange rate API error: {error_type}")
                return f"Could not fetch exchange rate: {error_type}"

        except Exception as e:
            logging.error(f"Exchange rate API error: {str(e)}")
            return f"Error fetching exchange rate: {str(e)}"

    def add_transaction(self, user_id: int, amount: float, currency: str, category: str, 
                       type: str, description: str, date: str = None, time: str = None) -> str:
        try:
            current_datetime = datetime.utcnow()
            
            # Parse date and time
            if date:
                transaction_date = datetime.strptime(date, "%Y-%m-%d")
            else:
                transaction_date = current_datetime.date()
                
            if time:
                transaction_time = datetime.strptime(time, "%H:%M").time()
            else:
                transaction_time = current_datetime.time()
                
            transaction_datetime = datetime.combine(transaction_date, transaction_time)
            
            # Validate inputs
            if type.lower() not in ['income', 'expense']:
                return "Invalid transaction type. Must be 'income' or 'expense'."
                
            if not currency or len(currency) != 3:
                return "Invalid currency code. Must be a 3-letter code (e.g., USD)."
                
            # Create and save transaction
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
            
            return f"{type.capitalize()} of {amount} {currency.upper()} for '{description}' added successfully at {transaction_datetime.strftime('%Y-%m-%d %H:%M')}."
            
        except Exception as e:
            logging.error(f"Database error in add_transaction: {str(e)}")
            db.session.rollback()
            return f"Failed to add transaction: {str(e)}"

    def get_total_by_type(self, user_id: int, transaction_type: str, 
                         start_date: str, end_date: str, target_currency: str = 'USD') -> float | str:
        try:
            start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            
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
                    rate = self.get_exchange_rate(tx.currency, target_currency)
                    if isinstance(rate, float) and rate > 0:
                        total_in_target_currency += tx.amount * rate
                    else:
                        logging.warning(f"Could not convert {tx.amount} {tx.currency} to {target_currency}")
                        return f"Could not calculate total in {target_currency} because conversion for {tx.currency} failed."
            
            return total_in_target_currency
            
        except ValueError:
            return "Invalid date format. Please use YYYY-MM-DD for start and end dates."
        except Exception as e:
            logging.error(f"Error in get_total_by_type: {str(e)}")
            return f"Error calculating total: {str(e)}" 