# app/services/exchange_service.py
import requests
import logging
from flask import current_app # To access app.config

def get_exchange_rate(from_currency: str, to_currency: str) -> float | str:
    """
    Fetches the exchange rate between two currencies.
    Returns the rate as a float or an error message string.
    """
    api_key = current_app.config.get('EXCHANGE_RATE_API_KEY')
    api_url = current_app.config.get('EXCHANGE_RATE_API_URL')

    if not current_app.config.get('EXCHANGE_RATE_API_ENABLED'):
         logging.warning("Exchange rate service disabled by config.")
         return "Exchange rate service is currently unavailable."

    try:
        url = f"{api_url}{api_key}/pair/{from_currency.upper()}/{to_currency.upper()}"
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        if data.get('result') == 'success':
            return data['conversion_rate']
        else:
            error_type = data.get('error-type', 'Unknown error')
            logging.error(f"Exchange rate API responded with an error: {error_type} for {from_currency} to {to_currency}")
            if error_type == 'unknown-code':
                return f"One or both currency codes ('{from_currency}', '{to_currency}') are invalid or not supported."
            return f"Could not fetch exchange rate: {error_type}"

    except requests.Timeout:
        logging.error("Exchange rate API request timed out.")
        return "Exchange rate service timed out. Please try again."
    except requests.RequestException as e:
        logging.error(f"Exchange rate API error: {str(e)}", exc_info=True)
        if e.response is not None and e.response.status_code == 404:
             return f"One or both currency codes ('{from_currency}', '{to_currency}') are invalid."
        return f"Error fetching exchange rate: {str(e)}"
    except Exception as e:
        logging.error(f"An unexpected error occurred fetching exchange rate: {str(e)}", exc_info=True)
        return f"An unexpected error occurred with the exchange rate service."