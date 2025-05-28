from flask import Blueprint, jsonify, request, render_template
from app.services.ai_service import AIService
from app.models.chat_history import ChatHistory
from app import db
import logging
import os

chat_bp = Blueprint('chat', __name__)

@chat_bp.route('/chat', methods=['POST'])
def chat():
    user_id = 1  # For now, hardcoded user_id
    data = request.get_json()
    
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
        
    user_message = data['message']
    if not user_message.strip():
        return jsonify({'response': "Please type a message to the assistant."})
    
    # Get AI response
    ai_service = AIService(os.getenv('GEMINI_API_KEY'))
    ai_response = ai_service.handle_query(user_id, user_message)
    
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
    
    return jsonify({'response': ai_response})

@chat_bp.route('/chat-history', methods=['GET'])
def get_chat_history():
    user_id = 1  # For now, hardcoded user_id
    try:
        history = ChatHistory.query.filter_by(user_id=user_id)\
            .order_by(ChatHistory.timestamp.desc())\
            .limit(50)\
            .all()
        
        formatted_history = [{
            'message': entry.message,
            'response': entry.response,
            'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        } for entry in reversed(history)]
        
        return jsonify({'history': formatted_history})
    except Exception as e:
        logging.error(f"Error retrieving chat history: {str(e)}")
        return jsonify({'error': 'Could not retrieve chat history'}), 500

@chat_bp.route('/chat-page', methods=['GET'])
def chat_page():
    return render_template('chat.html') 