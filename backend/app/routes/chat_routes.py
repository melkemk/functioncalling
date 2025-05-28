from flask import Blueprint, request, jsonify, render_template
from app.models.models import ChatHistory, Transaction
from app import db
from datetime import datetime
import google.generativeai as genai
import os
from app.services.chat_service import ChatService
from app.services.transaction_service import TransactionService
import logging

chat_bp = Blueprint('chat', __name__)

def process_transaction(message, user_id):
    try:
        parts = message.lower().split()
        if 'add income' in message.lower():
            amount = float(parts[2])
            currency = parts[3].upper()
            category = parts[6] if len(parts) > 6 else 'general'
            description = ' '.join(parts[8:]) if len(parts) > 8 else category
            
            transaction = Transaction(
                user_id=user_id,
                amount=amount,
                currency=currency,
                category=category,
                type='income',
                description=description,
                date=datetime.utcnow()
            )
            db.session.add(transaction)
            db.session.commit()
            
            return f"OK. Income of {amount} {currency} for '{category}' added successfully at {transaction.date.strftime('%Y-%m-%d %H:%M')}."
            
        elif 'add expense' in message.lower():
            amount = float(parts[2])
            currency = parts[3].upper()
            category = parts[6] if len(parts) > 6 else 'general'
            description = ' '.join(parts[8:]) if len(parts) > 8 else category
            
            transaction = Transaction(
                user_id=user_id,
                amount=amount,
                currency=currency,
                category=category,
                type='expense',
                description=description,
                date=datetime.utcnow()
            )
            db.session.add(transaction)
            db.session.commit()
            
            return f"OK. Expense of {amount} {currency} for '{category}' added successfully at {transaction.date.strftime('%Y-%m-%d %H:%M')}."
            
    except Exception as e:
        db.session.rollback()
        return f"I apologize, but I couldn't process the transaction: {str(e)}"

@chat_bp.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages and process them through the AI service."""
    try:
        data = request.get_json()
        if not data or 'message' not in data or 'user_id' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
            
        user_id = data['user_id']
        message = data['message']
        
        # Process the message
        response = ChatService.process_message(user_id, message)
        
        # Save the interaction
        ChatService.save_chat_history(user_id, message, response)
        
        return jsonify({
            'response': response,
            'user_id': user_id
        })
        
    except Exception as e:
        logging.error(f"Error in chat endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/chat/history', methods=['GET'])
def get_chat_history():
    """Retrieve chat history for a user."""
    try:
        user_id = request.args.get('user_id')
        limit = request.args.get('limit', default=50, type=int)
        
        if not user_id:
            return jsonify({'error': 'Missing user_id parameter'}), 400
            
        history = ChatService.get_chat_history(user_id, limit)
        return jsonify({'history': history})
        
    except Exception as e:
        logging.error(f"Error retrieving chat history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/chat/transaction', methods=['POST'])
def process_transaction():
    """Process a transaction request from the chat interface."""
    try:
        data = request.get_json()
        if not data or 'user_id' not in data or 'message' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
            
        user_id = data['user_id']
        message = data['message']
        
        # Process the message to extract transaction details
        response = ChatService.process_message(user_id, message)
        
        # If the response indicates a successful transaction, save it
        if "successfully" in response.lower():
            # Save the chat interaction
            ChatService.save_chat_history(user_id, message, response)
            
        return jsonify({
            'response': response,
            'user_id': user_id
        })
        
    except Exception as e:
        logging.error(f"Error processing transaction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/chat-page')
def chat_page():
    return render_template('chat.html') 