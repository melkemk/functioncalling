from datetime import datetime, timedelta
import logging
from app.models.models import Transaction
from app.services.transaction_service import TransactionService
from app.services.exchange_service import ExchangeRateService

class ReportService:
    """Service for generating financial reports and analytics."""
    
    @staticmethod
    def generate_monthly_summary(user_id: int, year: int, month: int, target_currency: str = 'USD') -> dict:
        """
        Generate a monthly financial summary.
        
        Args:
            user_id (int): The ID of the user
            year (int): The year to analyze
            month (int): The month to analyze (1-12)
            target_currency (str, optional): The currency to convert amounts to. Defaults to 'USD'.
            
        Returns:
            dict: Monthly summary including income, expenses, and net
        """
        try:
            # Calculate date range
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1)
            else:
                end_date = datetime(year, month + 1, 1)
                
            # Get totals
            income = TransactionService.get_total_by_type(
                user_id, 'income', 
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d'),
                target_currency
            )
            
            expenses = TransactionService.get_total_by_type(
                user_id, 'expense',
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d'),
                target_currency
            )
            
            # Calculate net
            if isinstance(income, (int, float)) and isinstance(expenses, (int, float)):
                net = income - expenses
            else:
                net = "Could not calculate net due to conversion errors"
                
            return {
                'period': f"{start_date.strftime('%B %Y')}",
                'income': income,
                'expenses': expenses,
                'net': net,
                'currency': target_currency
            }
            
        except Exception as e:
            logging.error(f"Error generating monthly summary: {str(e)}")
            return {
                'error': f"Failed to generate monthly summary: {str(e)}"
            }
    
    @staticmethod
    def generate_category_breakdown(user_id: int, start_date: str, end_date: str, 
                                  transaction_type: str = 'expense', target_currency: str = 'USD') -> dict:
        """
        Generate a breakdown of transactions by category.
        
        Args:
            user_id (int): The ID of the user
            start_date (str): Start date in YYYY-MM-DD format
            end_date (str): End date in YYYY-MM-DD format
            transaction_type (str, optional): Type of transactions to analyze. Defaults to 'expense'.
            target_currency (str, optional): The currency to convert amounts to. Defaults to 'USD'.
            
        Returns:
            dict: Category breakdown with totals
        """
        try:
            # Get transactions
            transactions = Transaction.query.filter(
                Transaction.user_id == user_id,
                Transaction.type == transaction_type.lower(),
                Transaction.date >= datetime.strptime(start_date, '%Y-%m-%d'),
                Transaction.date < datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            ).all()
            
            # Group by category
            categories = {}
            total = 0
            
            for tx in transactions:
                category = tx.category or 'Uncategorized'
                amount = tx.amount
                
                # Convert to target currency if needed
                if tx.currency.upper() != target_currency.upper():
                    rate = ExchangeRateService.get_exchange_rate(tx.currency, target_currency)
                    if isinstance(rate, float) and rate > 0:
                        amount *= rate
                    else:
                        logging.warning(f"Could not convert {tx.amount} {tx.currency} to {target_currency}")
                        continue
                
                if category in categories:
                    categories[category] += amount
                else:
                    categories[category] = amount
                    
                total += amount
            
            # Calculate percentages
            breakdown = {
                'categories': {
                    category: {
                        'amount': amount,
                        'percentage': (amount / total * 100) if total > 0 else 0
                    }
                    for category, amount in categories.items()
                },
                'total': total,
                'currency': target_currency,
                'period': f"{start_date} to {end_date}"
            }
            
            return breakdown
            
        except Exception as e:
            logging.error(f"Error generating category breakdown: {str(e)}")
            return {
                'error': f"Failed to generate category breakdown: {str(e)}"
            }
    
    @staticmethod
    def generate_trend_analysis(user_id: int, months: int = 6, target_currency: str = 'USD') -> dict:
        """
        Generate a trend analysis over multiple months.
        
        Args:
            user_id (int): The ID of the user
            months (int, optional): Number of months to analyze. Defaults to 6.
            target_currency (str, optional): The currency to convert amounts to. Defaults to 'USD'.
            
        Returns:
            dict: Monthly trends for income and expenses
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30 * months)
            
            # Get monthly summaries
            trends = []
            current_date = start_date
            
            while current_date <= end_date:
                summary = ReportService.generate_monthly_summary(
                    user_id,
                    current_date.year,
                    current_date.month,
                    target_currency
                )
                
                if 'error' not in summary:
                    trends.append({
                        'month': current_date.strftime('%Y-%m'),
                        'income': summary['income'],
                        'expenses': summary['expenses'],
                        'net': summary['net']
                    })
                
                # Move to next month
                if current_date.month == 12:
                    current_date = datetime(current_date.year + 1, 1, 1)
                else:
                    current_date = datetime(current_date.year, current_date.month + 1, 1)
            
            return {
                'trends': trends,
                'currency': target_currency,
                'period': f"{start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}"
            }
            
        except Exception as e:
            logging.error(f"Error generating trend analysis: {str(e)}")
            return {
                'error': f"Failed to generate trend analysis: {str(e)}"
            } 