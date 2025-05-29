# app/services/datetime_service.py
from datetime import datetime
import logging

def get_current_datetime() -> dict:
    """
    Get the current date and time using datetime.now().
    Returns a dictionary with date and time information suitable for AI tools.
    """
    try:
        dt = datetime.now()
        return {
            'date': dt.strftime('%Y-%m-%d'),
            'time': dt.strftime('%H:%M'),
            'day_name': dt.strftime('%A'),
            'timezone': 'Local' # Placeholder, replace with actual timezone logic if needed
        }
    except Exception as e:
        logging.error(f"Error getting current time: {str(e)}", exc_info=True)
        return {"error": f"Error getting current time: {str(e)}"}