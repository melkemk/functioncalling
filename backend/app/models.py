# app/models.py
from . import db # Import the db instance from the main app package (__init__.py)
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Define relationships on the "one" side (User)
    # backref='user' creates a 'user' property on the Transaction model
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    # backref='user' creates a 'user' property on the ChatHistory model
    chat_history = db.relationship('ChatHistory', backref='user', lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # This is the Foreign Key column linking to the User model
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    category = db.Column(db.String(50))
    type = db.Column(db.String(10), nullable=False) # 'income' or 'expense'
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(200))

    # REMOVE the explicit relationship definition here:
    # user = db.relationship('User', backref=db.backref('transaction', lazy=True))
    # The 'user' property will be created automatically by the backref on the User model

    def __repr__(self):
        return f"<Transaction {self.id} ({self.type}) {self.amount} {self.currency}>"

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # This is the Foreign Key column linking to the User model
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # REMOVE the explicit relationship definition here:
    # user = db.relationship('User', backref=db.backref('chat_entry', lazy=True))
    # The 'user' property will be created automatically by the backref on the User model

    def __repr__(self):
        return f"<ChatHistory {self.id} user:{self.user_id} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}>"