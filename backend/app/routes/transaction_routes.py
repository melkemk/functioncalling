from flask import Blueprint, request, jsonify
from app.services.transaction_service import TransactionService
from app.services.report_service import ReportService
import logging

transaction_bp = Blueprint('transaction', __name__)

@transaction_bp.route('/transaction', methods=['POST'])
def add_transaction():
    """Add a new transaction."""
    try:
        data = request.get_json()
        required_fields = ['user_id', 'amount', 'currency', 'category', 'type', 'description']
        
        if not data or not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400
            
        response = TransactionService.add_transaction(
            user_id=data['user_id'],
            amount=data['amount'],
            currency=data['currency'],
            category=data['category'],
            type=data['type'],
            description=data['description'],
            date=data.get('date'),
            time=data.get('time')
        )
        
        if 'successfully' in response.lower():
            return jsonify({'message': response}), 201
        else:
            return jsonify({'error': response}), 400
            
    except Exception as e:
        logging.error(f"Error adding transaction: {str(e)}")
        return jsonify({'error': str(e)}), 500

@transaction_bp.route('/transaction/summary', methods=['GET'])
def get_transaction_summary():
    """Get transaction summary for a period."""
    try:
        user_id = request.args.get('user_id')
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)
        currency = request.args.get('currency', default='USD')
        
        if not all([user_id, year, month]):
            return jsonify({'error': 'Missing required parameters'}), 400
            
        summary = ReportService.generate_monthly_summary(user_id, year, month, currency)
        
        if 'error' in summary:
            return jsonify({'error': summary['error']}), 400
            
        return jsonify(summary)
        
    except Exception as e:
        logging.error(f"Error getting transaction summary: {str(e)}")
        return jsonify({'error': str(e)}), 500

@transaction_bp.route('/transaction/breakdown', methods=['GET'])
def get_category_breakdown():
    """Get category breakdown for a period."""
    try:
        user_id = request.args.get('user_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        transaction_type = request.args.get('type', default='expense')
        currency = request.args.get('currency', default='USD')
        
        if not all([user_id, start_date, end_date]):
            return jsonify({'error': 'Missing required parameters'}), 400
            
        breakdown = ReportService.generate_category_breakdown(
            user_id, start_date, end_date, transaction_type, currency
        )
        
        if 'error' in breakdown:
            return jsonify({'error': breakdown['error']}), 400
            
        return jsonify(breakdown)
        
    except Exception as e:
        logging.error(f"Error getting category breakdown: {str(e)}")
        return jsonify({'error': str(e)}), 500

@transaction_bp.route('/transaction/trends', methods=['GET'])
def get_trend_analysis():
    """Get trend analysis for a period."""
    try:
        user_id = request.args.get('user_id')
        months = request.args.get('months', default=6, type=int)
        currency = request.args.get('currency', default='USD')
        
        if not user_id:
            return jsonify({'error': 'Missing user_id parameter'}), 400
            
        trends = ReportService.generate_trend_analysis(user_id, months, currency)
        
        if 'error' in trends:
            return jsonify({'error': trends['error']}), 400
            
        return jsonify(trends)
        
    except Exception as e:
        logging.error(f"Error getting trend analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500 