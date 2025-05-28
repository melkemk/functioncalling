import logging
import google.generativeai as genai
from datetime import datetime
from app.models.chat_history import ChatHistory
from app import db

class AIService:
    def __init__(self, api_key):
        self.api_key = api_key
        if not api_key:
            logging.error("GEMINI_API_KEY not found in environment variables. AI features will be disabled.")
        else:
            genai.configure(api_key=api_key)

    def handle_query(self, user_id: int, query_text: str) -> str:
        if not self.api_key:
            return "AI Assistant is not available: API key not configured."

        try:
            model = genai.GenerativeModel(
                model_name='gemini-1.5-flash-latest',
                system_instruction=self._get_system_instruction()
            )

            chat = model.start_chat(history=[])
            response = chat.send_message(query_text, tools=[{'function_declarations': self._get_tool_declarations()}])
            
            # Process response and handle function calls
            final_text = self._process_response(response, user_id, query_text)
            return final_text

        except Exception as e:
            logging.error(f"Error in AI query handling: {str(e)}", exc_info=True)
            return f"An error occurred while processing your request: {str(e)}"

    def _get_system_instruction(self) -> str:
        return """
        You are a precise, proactive, and highly autonomous financial assistant.
        Your primary role is to help users manage and understand their finances.
        You MUST proactively interpret user queries to extract necessary parameters.
        DO NOT ask clarifying questions if the information can be reasonably inferred.
        """

    def _get_tool_declarations(self) -> list:
        return [
            {
                'name': 'get_exchange_rate',
                'description': 'Get the current exchange rate between two currencies.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'from_currency': {'type': 'string'},
                        'to_currency': {'type': 'string'}
                    },
                    'required': ['from_currency', 'to_currency']
                }
            },
            # Add other tool declarations here
        ]

    def _process_response(self, response, user_id: int, query_text: str) -> str:
        # Process the response and handle any function calls
        # This is a simplified version - you'll need to implement the full logic
        if response and response.parts:
            final_text = ""
            for part in response.parts:
                if hasattr(part, 'text') and part.text:
                    final_text += part.text
            return final_text
        return "I received your message, but I'm not sure how to respond." 