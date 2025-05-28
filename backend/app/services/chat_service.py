import google.generativeai as genai
import logging
from datetime import datetime
from app.models.models import ChatHistory
from app.config.config import GEMINI_API_KEY
from app import db
from app.services.exchange_service import ExchangeRateService
from app.services.transaction_service import TransactionService
from app.services.report_service import ReportService
import re
import time

class ChatService:
    """Service for handling AI chat interactions and chat history."""
    
    SYSTEM_INSTRUCTION = """You are a precise, proactive, and highly autonomous financial assistant named 'FinAssist'. 
Your primary role is to help users manage and understand their finances by intelligently calling the available tools. 
You MUST proactively interpret user queries to extract all necessary parameters for tool calls.

TOOL CALLING - GENERAL RULES:
For each tool, its description specifies 'required' parameters. You MUST ensure all required parameters have values before successfully calling the tool.
  - If the user's query provides a value, extract and use it.
  - If a value can be reasonably and confidently inferred (e.g., 'dollars' implies 'USD', 'today' for a date if unspecified for a new transaction), infer it.
  - If a required parameter's value is missing from the user's query AND cannot be confidently inferred:
    - For `add_transaction`: If 'category' or 'description' are missing, you MUST explicitly ask the user for *both* specific pieces of missing information *before* calling the tool. For other missing required fields (`amount`, `currency`, `type`), if not provided or inferable, ask the user clearly for the missing information.
    - For `get_financial_summary`: If `transaction_type`, `start_date`, or `end_date` are missing and not inferable, ask the user for the specific missing information.
    - For other tools: If required parameters are missing and not inferable, inform the user what information is needed.
DO NOT call a tool if its required parameters are still missing after your extraction/inference and you haven't received the needed information from the user.
DO NOT ask clarifying questions for information that *can* be reasonably inferred or is listed as optional and not provided.
If the user provides information that allows you to perform a tool action, confirm the action *after* it's done based on the tool's result.

CRITICAL INSTRUCTION FOR CURRENT DATE/TIME QUERIES AND DEFAULTS:
When users ask about the current date, time, or day of the week, ALWAYS use the current system time.
Additionally, when a tool requires the current date or time (e.g., defaulting date/time for `add_transaction` when not specified, or calculating relative dates like 'yesterday', 'last month'), you MUST use the current system time to determine the parameter values.

CRITICAL INSTRUCTION FOR CURRENCY CODES:
When a user query involves country names, specific currencies by name, or common currency understanding (e.g., 'dollars' usually means USD, 'pounds' usually GBP, 'euro' is EUR, 'Birr' usually ETB),
you MUST independently identify and use the correct 3-letter ISO currency codes (e.g., USD, ETB, KES, EUR, GBP, JPY, CNY, INR, CAD, AUD). ALWAYS use UPPERCASE for currency codes.
DO NOT ask the user for these codes if the country or currency name is given or clearly implied.

DATE AND TIME HANDLING:
Tool functions require dates in YYYY-MM-DD format and times in HH:MM format.
You MUST autonomously convert all natural language date and time references into these precise formats. Do not ask the user for reformatting if your inference is sound.

RESPONSE GUIDELINES:
1. After successfully calling a tool, present the results in a clear, human-readable sentence or summary. Always state currency explicitly if currency information is involved.
2. If a tool function returns an error string, explain the error clearly to the user in simple terms.
3. Be concise. A simple confirmation is often sufficient after a successful action.
4. If required information is missing *and not inferable*, ask for it *before* calling the tool, specifying *exactly* what is needed.
5. After executing a function and receiving its result, ALWAYS provide a final textual response to the user summarizing the outcome or presenting the data.
6. If the user asks a simple non-financial question (like 'hello', 'how are you'), respond appropriately without trying to call a financial tool."""

    @staticmethod
    def process_message(user_id: int, message: str) -> str:
        """
        Process a user message and generate an AI response.
        If the message is about time, exchange rates, adding transactions, or generating reports, use backend services.
        Otherwise, use Gemini.
        """
        if not GEMINI_API_KEY:
            return "AI Assistant is not available: API key not configured."

        # --- INTENT DETECTION ---
        msg = message.lower().strip()
        # 1. Time intent
        if any(kw in msg for kw in ["what time is it", "current time", "time now", "date today", "what's the date", "today's date", "day of week"]):
            now = datetime.now()
            return f"The current date and time is {now.strftime('%Y-%m-%d %H:%M')}."
        # 2. Exchange rate intent
        match = re.search(r'exchange rate from (\w{3}|[a-zA-Z]+) to (\w{3}|[a-zA-Z]+)', msg)
        if match:
            from_cur = match.group(1).upper()
            to_cur = match.group(2).upper()
            # Try to convert currency names to codes if needed
            currency_map = {'dollars': 'USD', 'usd': 'USD', 'euros': 'EUR', 'euro': 'EUR', 'eur': 'EUR', 'pounds': 'GBP', 'gbp': 'GBP', 'birr': 'ETB', 'etb': 'ETB'}
            from_cur = currency_map.get(from_cur.lower(), from_cur)
            to_cur = currency_map.get(to_cur.lower(), to_cur)
            rate = ExchangeRateService.get_exchange_rate(from_cur, to_cur)
            if isinstance(rate, float):
                return f"The current exchange rate from {from_cur} to {to_cur} is {rate:.4f}."
            else:
                return f"Could not fetch exchange rate: {rate}"
        # 3. Add expense intent
        match = re.search(r'add expense (\d+(?:\.\d+)?) (\w{3}|[a-zA-Z]+) (?:for|category) (\w+)', msg)
        if match:
            amount = float(match.group(1))
            currency = match.group(2).upper()
            category = match.group(3)
            currency_map = {'dollars': 'USD', 'usd': 'USD', 'euros': 'EUR', 'euro': 'EUR', 'eur': 'EUR', 'pounds': 'GBP', 'gbp': 'GBP', 'birr': 'ETB', 'etb': 'ETB'}
            currency = currency_map.get(currency.lower(), currency)
            response = TransactionService.add_transaction(user_id, amount, currency, category, 'expense', f"Expense for {category}")
            return response
        # 4. Add income intent
        match = re.search(r'add income (\d+(?:\.\d+)?) (\w{3}|[a-zA-Z]+) (?:for|category) (\w+)', msg)
        if match:
            amount = float(match.group(1))
            currency = match.group(2).upper()
            category = match.group(3)
            currency_map = {'dollars': 'USD', 'usd': 'USD', 'euros': 'EUR', 'euro': 'EUR', 'eur': 'EUR', 'pounds': 'GBP', 'gbp': 'GBP', 'birr': 'ETB', 'etb': 'ETB'}
            currency = currency_map.get(currency.lower(), currency)
            response = TransactionService.add_transaction(user_id, amount, currency, category, 'income', f"Income for {category}")
            return response
        # 5. Generate report intent
        if any(kw in msg for kw in ["generate report", "show report", "get report"]):
            now = datetime.now()
            summary = ReportService.generate_monthly_summary(user_id, now.year, now.month, 'USD')
            if 'error' in summary:
                return f"Could not generate report: {summary['error']}"
            return f"Report for {summary['period']}: Income: {summary['income']} USD, Expenses: {summary['expenses']} USD, Net: {summary['net']} USD."
        # 6. Fallback to Gemini for other queries
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash-latest',
                generation_config={
                    'temperature': 0.7,
                    'top_p': 0.8,
                    'top_k': 40,
                }
            )
            history = ChatHistory.query.filter_by(user_id=user_id)\
                .order_by(ChatHistory.timestamp.desc())\
                .limit(5)\
                .all()
            context = f"System: {ChatService.SYSTEM_INSTRUCTION}\n\n"
            context += "\n".join([f"User: {h.message}\nAssistant: {h.response}" for h in reversed(history)])
            chat = model.start_chat(history=[])
            response = chat.send_message(f"{context}\nUser: {message}")
            if response and response.text:
                return response.text
            else:
                return "I received your message, but I'm not sure how to help with that. Could you please rephrase or ask a specific financial question?"
        except Exception as e:
            logging.error(f"Error in chat processing: {str(e)}")
            return f"I apologize, but I encountered an error: {str(e)}"
    
    @staticmethod
    def save_chat_history(user_id: int, message: str, response: str) -> bool:
        """
        Save a chat interaction to the history.
        
        Args:
            user_id (int): The ID of the user
            message (str): The user's message
            response (str): The AI's response
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            chat_entry = ChatHistory(
                user_id=user_id,
                message=message,
                response=response,
                timestamp=datetime.utcnow()
            )
            db.session.add(chat_entry)
            db.session.commit()
            return True
        except Exception as e:
            logging.error(f"Error saving chat history: {str(e)}")
            db.session.rollback()
            return False
    
    @staticmethod
    def get_chat_history(user_id: int, limit: int = 50) -> list:
        """
        Retrieve chat history for a user.
        
        Args:
            user_id (int): The ID of the user
            limit (int, optional): Maximum number of messages to retrieve. Defaults to 50.
            
        Returns:
            list: List of chat history entries
        """
        try:
            history = ChatHistory.query.filter_by(user_id=user_id)\
                .order_by(ChatHistory.timestamp.desc())\
                .limit(limit)\
                .all()
            
            return [{
                'message': entry.message,
                'response': entry.response,
                'timestamp': entry.timestamp.isoformat()
            } for entry in reversed(history)]
            
        except Exception as e:
            logging.error(f"Error retrieving chat history: {str(e)}")
            return [] 