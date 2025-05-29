# app/routes/api_routes.py
from flask import request, jsonify, send_file, url_for, Blueprint, current_app
import logging
import os
import io # Needed for BytesIO
from datetime import datetime

# Import necessary components from the app package and services
from .. import db # Need db for ChatHistory session operations
from ..models import ChatHistory, Transaction # Need models for querying
from ..services.ai_service import handle_ai_query # AI handler service
from ..services.financial_service import generate_pdf_report, generate_csv_data # Financial service functions

# Create a Blueprint named 'api' with a URL prefix /api
api = Blueprint('api', __name__, url_prefix='/api')

@api.route('/chat', methods=['POST'])
def chat_endpoint():
    """Handles chat messages from the frontend, interacts with the AI service."""
    user_id = 1 # Assuming single user for now

    data = request.get_json()

    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400

    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'response': "Please type a message to the assistant."})

    logging.info(f"Received chat message from user {user_id}: {user_message}")

    # Call the AI service function to get the response
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
        logging.info(f"Chat history stored for user {user_id}")
    except Exception as e:
        logging.error(f"Error storing chat history for user {user_id}: {str(e)}", exc_info=True)
        # Log the error but don't necessarily fail the request

    # Return the AI response to the frontend
    return jsonify({'response': ai_response})

@api.route('/chat-history', methods=['GET'])
def get_chat_history_endpoint():
    """Retrieves recent chat history for the user."""
    user_id = 1 # Assuming single user for now
    try:
        # Get the last 50 chat messages, ordered chronologically for display
        history = ChatHistory.query.filter_by(user_id=user_id)\
            .order_by(ChatHistory.timestamp.asc())\
            .limit(50)\
            .all()

        # Format the history for JSON response
        formatted_history = [{
            'message': entry.message,
            'response': entry.response,
            'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for entry in history]

        logging.info(f"Retrieved {len(formatted_history)} chat history entries for user {user_id}")
        return jsonify({'history': formatted_history})

    except Exception as e:
        logging.error(f"Error retrieving chat history for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({'error': 'Could not retrieve chat history'}), 500

@api.route('/reports/pdf/<filename>')
def download_pdf_report_file(filename: str):
    """Serves a previously generated PDF report file."""
    # Basic security check to prevent directory traversal and check filename prefix
    user_id = 1 # Replace with actual user ID logic if securing by user
    valid_prefix_user = f"financial_report_user_{user_id}_".replace(' ', '_') # Example for user 1
    valid_prefix_demouser = f"financial_report_demouser_".replace(' ', '_') # Example for demo user

    # Ensure filename starts with an expected prefix and contains no directory traversal attempts
    if not (filename.startswith(valid_prefix_user) or filename.startswith(valid_prefix_demouser)) or ".." in filename or "/" in filename or "\\" in filename:
        logging.warning(f"Attempted invalid PDF filename access: {filename}")
        return jsonify({"error": "Report not found or access denied."}), 404

    # Construct the safe path to the file (assuming reports are in the current working directory)
    safe_path = os.path.join(os.getcwd(), filename)

    # Check if the file exists and is actually a file
    if not os.path.exists(safe_path) or not os.path.isfile(safe_path):
        logging.warning(f"Attempt to access non-existent PDF report: {filename} at path {safe_path}")
        return jsonify({"error": "Report file not found on server."}), 404

    logging.info(f"Serving PDF file: {filename}")
    try:
        # send_file correctly handles mimetype and attachments
        return send_file(safe_path, as_attachment=True)
    except Exception as e:
        error_msg = f"Error sending PDF file {filename}: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return jsonify({"error": "Could not send report file."}), 500


@api.route('/request-pdf-report', methods=['GET'])
def request_pdf_report_endpoint():
    """Triggers the generation of a PDF report and returns a download URL."""
    user_id = 1 # Assuming single user for now
    try:
        # Call the service function to generate the PDF. It returns the filename on success.
        filename = generate_pdf_report(user_id)

        if not filename:
            # This case shouldn't happen if generate_pdf_report raises on error,
            # but included as a safeguard.
            raise Exception("PDF generation failed - no filename returned by service.")

        # Verify the file exists after generation (optional, adds robustness)
        if not os.path.exists(filename):
             raise Exception(f"Generated PDF file not found on disk after service call: {filename}")

        # Generate the URL for the download route
        # url_for takes the endpoint name (function name within blueprint), filename parameter, and _external=True for full URL
        download_url = url_for('api.download_pdf_report_file', filename=filename, _external=True) # 'api' is the blueprint name

        logging.info(f"PDF report generated and download URL created for user {user_id}: {download_url}")

        # Return JSON response with success message and download URL
        return jsonify({
            "message": f"PDF report '{filename}' generated successfully.",
            "download_url": download_url,
            "filename": filename # Also return filename, might be useful for frontend
        })

    except Exception as e:
        # Catch exceptions raised by generate_pdf_report service function
        error_msg = f"Could not generate PDF report for user {user_id}: {str(e)}"
        logging.error(error_msg, exc_info=True)
        return jsonify({"error": error_msg}), 500 # Return an appropriate error response


@api.route('/reports/csv', methods=['GET'])
def get_csv_report_endpoint():
    """Generates and serves a CSV report of all transactions for the user."""
    user_id = 1 # Assuming single user for now
    # Define the output filename for the download
    output_filename = f"financial_transactions_user_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"

    try:
        # Call the service function to generate the CSV data buffer
        csv_buffer = generate_csv_data(user_id)

        # Handle the case where the service function returned None (no data)
        if csv_buffer is None:
             logging.info(f"No transactions found for user {user_id} to generate CSV.")
             return jsonify({"message": "No transactions found for this user to export."}), 404 # HTTP 404 or 200 with message? 404 is common for 'not found' data.

        # Serve the BytesIO buffer as a file download
        logging.info(f"Serving CSV file: {output_filename} for user {user_id}")
        return send_file(
            csv_buffer,
            mimetype='text/csv',
            as_attachment=True,
            download_name=output_filename # Use download_name instead of filename for clarity
        )

    except Exception as e:
        # Catch exceptions raised by the generate_csv_data service function
        logging.error(f"Error generating or sending CSV for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to generate CSV report due to an internal error."}), 500