import requests
import logging
from app.config.config import EXCHANGE_RATE_API_URL, EXCHANGE_RATE_API_KEY

class ExchangeRateService:
    """Service for handling currency exchange rate operations."""
    
    @staticmethod
    def get_exchange_rate(from_currency: str, to_currency: str) -> float | str:
        """
        Get the current exchange rate between two currencies.
        
        Args:
            from_currency (str): The 3-letter currency code to convert from
            to_currency (str): The 3-letter currency code to convert to
            
        Returns:
            float | str: The exchange rate if successful, error message if failed
        """
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