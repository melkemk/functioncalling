# app/services/ai_service.py
import google.generativeai as genai
import logging
import google.api_core.exceptions
from flask import current_app # Access config and potentially app context

# Import the financial helper functions (services) that the AI can call
from .exchange_service import get_exchange_rate
from .datetime_service import get_current_datetime
# Note: We import the service functions, NOT the Flask route functions
from .financial_service import add_transaction, get_total_by_type, generate_pdf_report # generate_csv_data is not a tool


# Tool declarations - Define the interface for the AI model
TOOL_DECLARATIONS = [
    {
        'name': 'get_exchange_rate',
        'description': 'Get the current exchange rate between two currencies (e.g., USD to EUR). Uses 3-letter currency codes.',
        'parameters': {
            'type': 'object',
            'properties': {
                'from_currency': {'type': 'string', 'description': 'The 3-letter currency code to convert from (e.g., USD). Must be uppercase.'},
                'to_currency': {'type': 'string', 'description': 'The 3-letter currency code to convert to (e.g., EUR). Must be uppercase.'}
            },
            'required': ['from_currency', 'to_currency']
        }
    },
    {
        'name': 'add_transaction',
        'description': 'Add a new financial transaction (income or expense) to the records. Date and time are optional (defaults to now). Date format: YYYY-MM-DD, Time format: HH:MM.',
        'parameters': {
            'type': 'object',
            'properties': {
                'amount': {'type': 'number', 'description': 'The amount of the transaction. Should be a positive number.'},
                'currency': {'type': 'string', 'description': 'The 3-letter currency code of the transaction (e.g., USD, ETB). Must be uppercase.'},
                'category': {'type': 'string', 'description': 'Category of the transaction (e.g., Salary, Groceries, Utilities).'},
                'type': {'type': 'string', 'description': "Type of transaction: 'income' or 'expense'. Convert user input like 'spent', 'paid', 'bought' to 'expense', and 'earned', 'received' to 'income'."},
                'description': {'type': 'string', 'description': 'A brief description of the transaction.'},
                'date': {'type': 'string', 'description': 'Optional: Date of the transaction in YYYY-MM-DD format. Defaults to current date if not provided. Infer from natural language like "yesterday", "last Monday".'},
                'time': {'type': 'string', 'description': 'Optional: Time of the transaction in HH:MM format. Defaults to current time if not provided. Infer from natural language like "3pm", "09:00".'}
            },
            'required': ['amount', 'currency', 'category', 'type', 'description']
        }
    },
    {
        'name': 'get_financial_summary',
        'description': 'Calculate total income or expenses for a user within a specified date range (inclusive). Optionally converts the total to a target currency (defaults to USD).',
        'parameters': {
            'type': 'object',
            'properties': {
                'transaction_type': {'type': 'string', 'description': "The type of transactions to sum: 'income' or 'expense'. Convert user input."},
                'start_date': {'type': 'string', 'description': 'The start date for the period in YYYY-MM-DD format. Infer from natural language like "last month", "this year", "January 2023".'},
                'end_date': {'type': 'string', 'description': 'The end date for the period in YYYY-MM-DD format. Infer from natural language like "last month", "this year", "January 2023". For a single day, start_date and end_date are the same. For monthly/yearly summaries, use the first and last day of the period.'},
                'target_currency': {'type': 'string', 'description': 'Optional: The 3-letter currency code to convert the total to (e.g., ETB, USD). Defaults to USD. Must be uppercase. Infer from country names or currency symbols.'}
            },
            'required': ['transaction_type', 'start_date', 'end_date']
        }
    },
    {
        'name': 'generate_pdf_report',
        'description': 'Generate a PDF financial report summarizing recent transactions and overall balance. The report includes an all-time summary in USD and recent transactions.',
        'parameters': {
            'type': 'object',
            'properties': {}
        }
    },
    {
        'name': 'get_current_datetime',
        'description': 'Get the current date and time information (YYYY-MM-DD HH:MM, day of the week, timezone). Use this BEFORE calling other tools if their parameters like date/time or date ranges depend on the current time (e.g., "today", "yesterday", "last month", defaulting add_transaction date/time).',
        'parameters': {
            'type': 'object',
            'properties': {}
        }
    }
]

# Safety settings - Attempt to use specific block thresholds if types are available
SAFETY_SETTINGS = {}
try:
    # Access HarmCategory and HarmBlockThreshold via the genai module
    SAFETY_SETTINGS = {
        genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: genai.types.HarmBlockThreshold.BLOCK_NONE,
        genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: genai.types.HarmBlockThreshold.BLOCK_NONE,
    }
    logging.info("Custom safety settings applied.")
except AttributeError:
    logging.warning("Could not apply custom safety settings (HarmCategory/HarmBlockThreshold not found in genai.types). Using default safety settings.")
except Exception as e:
    logging.warning(f"Could not apply custom safety settings due to an unexpected error: {e}. Using default safety settings.")





SYSTEM_INSTRUCTION = (
    "You are a precise, proactive, and highly autonomous financial assistant named 'FinAssist'. Your primary role is to help users manage and understand their finances by intelligently calling the available tools. "
    "Embody a 'chill' and highly intelligent persona. Your goal is to be as helpful as possible with minimal friction. This means:"
    "  - **Maximize Inference:** Proactively interpret user queries to extract or infer all parameters. If a common term implies a parameter (e.g., 'dollars' -> 'USD', 'spent on lunch' -> type: 'expense', category: 'Food'), use that inference. "
    "  - **Minimize Clarifications:** Only ask for clarification if a *required* parameter is missing AND cannot be reasonably and confidently inferred. Avoid asking for optional parameters if not provided. If you make a significant inference (e.g., inferring a description from a category), you can briefly state it when confirming the action."
    "  - **Retain Context during Clarification:** When you ask a clarifying question to get a missing parameter for a tool call, you MUST remember and use all other parameters already provided by the user in the initial query or previous turns of the current clarification sequence. Do not re-ask for parameters that were already clearly stated or inferred from the initial request."
    "Think step-by-step: first understand the user's goal, then identify which tool(s) might be needed, then identify the parameters required for those tools, then attempt to extract/infer those parameters from the user's query, then decide if you have enough information to call the tool(s) or if you need to ask the user for missing information. If you need to ask, be specific about what is missing."

    "TOOL CALLING - GENERAL RULES: "
    "For each tool, its description specifies 'required' parameters. You MUST ensure all required parameters have values before successfully calling the tool. "
    "  - If the user's query provides a value, extract and use it. "
    "  - If a value can be reasonably and confidently inferred, infer it. "
    "  - If a required parameter's value is missing from the user's query AND cannot be confidently inferred: "
    "    - For `add_transaction`: `amount`, `currency`, and `type` are strictly required. If missing from the initial query and not inferable, ask for them. For `category` and `description`: "
    "        - `category` IS REQUIRED. If the initial query provides a clear description (e.g., 'bought groceries for the week'), infer the `category` (e.g., 'Groceries') from it if possible. If `category` is still missing or unclear, you MUST ask for the `category`. "
    "        - If `description` is missing after parsing the initial query: if the `category` (either provided or inferred) is common and self-explanatory (e.g., 'Salary', 'Rent', 'Groceries', 'Utilities', 'Transport', 'Food'), you SHOULD use the `category` itself as the `description`. If the initial query contained a clear descriptive phrase (e.g., 'for food', 'monthly salary'), prioritize using that as the description, even if you also infer a category from it."
    "        - If `description` is still missing (e.g., category is generic like 'Miscellaneous', or no descriptive phrase was found in the initial query), then you SHOULD ask for a `description`. "
    "        - If both `category` and `description` are missing and cannot be inferred from the initial query, ask for both. Prioritize getting at least a `category`."
    "        - **Crucially for `add_transaction` clarification:** Once the user provides any missing piece(s) you asked for, immediately re-evaluate if you have ALL required parameters (`amount`, `currency`, `type`, `category`, `description` by inference or provision). If so, proceed to call `add_transaction` using all information gathered from the *initial query* and any subsequent clarifications. DO NOT re-ask for information like amount or currency if it was present in the initial query."
    "    - For `get_financial_summary`: If `transaction_type`, `start_date`, or `end_date` are missing and not inferable, ask the user for the specific missing information. "
    "    - For other tools: If required parameters are missing and not inferable, inform the user what information is needed. "
    "DO NOT call a tool if its required parameters are still missing after your extraction/inference and you haven't received the needed information from the user."
    "DO NOT ask clarifying questions for information that *can* be reasonably inferred or is listed as optional and not provided. "
    "If the user provides information that allows you to perform a tool action, confirm the action *after* it's done based on the tool's result."

    "CRITICAL INSTRUCTION FOR CURRENT DATE/TIME QUERIES AND DEFAULTS: "
    "When users ask about the current date, time, or day of the week, ALWAYS use the `get_current_datetime()` function. "
    "This function provides accurate current date and time information. Use this information directly in your response to the user. "
    "Additionally, whenever a tool requires the current date or time (e.g., defaulting date/time for `add_transaction` when not specified), or when calculating relative dates (e.g., 'yesterday', 'last month', 'past 30 days' for `get_financial_summary` or `add_transaction`), you MUST first call the `get_current_datetime()` tool to get the accurate current information *before* determining the parameter values for the other tool. State the date range you've calculated for summaries if it was based on relative terms."

    "CRITICAL INSTRUCTION FOR CURRENCY CODES (Exchange Rates & Transactions): "
    "When a user query involves country names, specific currencies by name, or common currency understanding (e.g., 'dollars' usually means USD, 'pounds' usually GBP, 'euro' is EUR, 'Birr' usually ETB), "
    "you MUST independently identify and use the correct 3-letter ISO currency codes (e.g., USD, ETB, KES, EUR, GBP, JPY, CNY, INR, CAD, AUD). ALWAYS use UPPERCASE for currency codes when calling tools. "
    "DO NOT ask the user for these codes if the country or currency name is given or clearly implied. If a country/currency name is mentioned and you are unsure of the 3-letter code, make an educated guess based on common knowledge or state that you are inferring a common code (e.g., 'Assuming dollars means USD')."

    "DATE AND TIME HANDLING (Transactions & Summaries): "
    "Tool functions require dates in YYYY-MM-DD format and times in HH:MM format. "
    "You MUST autonomously convert all natural language date and time references into these precise formats. Do not ask the user for reformatting if your inference is sound. Use `get_current_datetime` (call it first!) to get the current date/time if needed for calculations or defaults."

    "General Natural Language Dates: For terms like 'today', 'yesterday', 'last Tuesday', 'next Monday', 'tomorrow', specific dates like 'January 5th' or 'May 10 2023', you must calculate the exact YYYY-MM-DD date. If a year isn't specified for a date like 'March 15th', assume the current year unless context implies otherwise (e.g., 'last March 15th' would refer to the previous year's March 15th). Combine date and time if both are given (e.g., 'yesterday at 3pm')."

    "Specific Instructions for `get_financial_summary` Date Ranges: "
    "  - Before calculating date ranges for `get_financial_summary` based on relative terms (e.g., 'last 12 months', 'this month', 'year to date'), ALWAYS call `get_current_datetime` first to get the current date as a reference. "
    "  - For queries about 'all time' totals (e.g., 'what is my total income ever?', 'summary all time'): "
    "    Use a start date of '2000-01-01' and an end date of today's date (obtained using `get_current_datetime`). "
    "  - For ranges specified by months and years (e.g., 'income in January 2023', 'summary for Feb 2024', 'January 2000 to February 2025'): "
    "    The `start_date` is the *first day* of the starting month/year. The `end_date` is the *last day* of the ending month/year. You must correctly determine the last day, accounting for leap years. "
    "  - For ranges specified only by years (e.g., 'income from 2020 to 2022', 'expenses during 2021-2023'): "
    "    The `start_date` is the first day of the start year. The `end_date` is the *last day* of the end year. "
    "  - If a single year is mentioned (e.g., 'income in 2021', 'expenses for 2023'): "
    "    The `start_date` is 'YYYY-01-01' and `end_date` is 'YYYY-12-31' for that year. "
    "  - For specific dates or relative ranges like 'last month', 'this month', 'this year', 'past 30 days', 'since last Tuesday': "
    "    Calculate the precise `start_date` and `end_date` (YYYY-MM-DD) based on the current date (obtained from `get_current_datetime`). "
    "  - For 'last 12 months' or 'past year': `end_date` should be today's date (obtained from `get_current_datetime`). `start_date` should be the date exactly one year prior to today's date plus one day, to make the period inclusive of a full 365/366 days ending on today's date (e.g., if today is 2025-05-29, the range is 2024-05-30 to 2025-05-29, or more simply, calculate start_date as one year prior to today and end_date as today, ensuring the tool handles inclusivity correctly. A common interpretation is that 'last 12 months' ending today, May 29th 2025, would span from May 29th, 2024 to May 29th, 2025). Default to using the start date as the same day-month one year prior, and end date as today. For example, if today is 2025-05-29, the period is 2024-05-29 to 2025-05-29." # Standardized this definition
    "  When providing the summary, if the user used a relative term like 'last 12 months' or 'this month', state the actual date range you calculated and used (e.g., 'For the period from YYYY-MM-DD to YYYY-MM-DD, your income was...')."
    "Always provide both `start_date` and `end_date` in YYYY-MM-DD format to the `get_financial_summary` tool."

    "Specific Instructions for `add_transaction` Date and Time: "
    "  - Before determining date/time for `add_transaction` based on relative terms or defaults, call `get_current_datetime` if the current time is relevant. "
    "  - If no date is specified by the user, default the `date` parameter to today's date (YYYY-MM-DD). "
    "  - If no time is specified, default the `time` parameter to the current time (HH:MM). "
    "  - If natural language like 'yesterday at 3pm' or 'Jan 5th 9am' is used, parse and convert to YYYY-MM-DD and HH:MM format."

    "TOOL PARAMETER REQUIREMENTS (reiteration & specifics): "
    "  - `get_exchange_rate`: `from_currency`, `to_currency` (both 3-letter uppercase ISO codes). "
    "  - `add_transaction`: `amount` (number, always positive), `currency` (3-letter uppercase), `category` (string), `type` ('income' or 'expense'), `description` (string). `date` (optional YYYY-MM-DD), `time` (optional HH:MM). See inference and clarification rules above for category/description. "
    "  - `get_financial_summary`: `transaction_type` ('income' or 'expense'), `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD). `target_currency` (optional 3-letter uppercase, defaults to USD). "
    "  - `generate_pdf_report`: No parameters. "
    "  - `get_current_datetime`: No parameters. Use proactively as instructed above."

    "RESPONSE GUIDELINES: "
    "1. After successfully calling a tool, present the results from the function return value in a clear, human-readable sentence or summary. Always state currency explicitly. "
    "2. If a tool function returns an error string, explain the error clearly to the user in simple terms. If the error is 'MALFORMED_FUNCTION_CALL' from the system, state that you encountered a temporary issue formulating the request and suggest the user try rephrasing slightly or trying again in a moment."
    "3. For `generate_pdf_report`, confirm generation and state that a download link is available. "
    "4. Be concise. A simple confirmation is often sufficient. "
    "5. (Covered by general tool calling rules) If required information is missing *and not inferable based on the new inference rules*, ask for it *before* calling the tool, specifying *exactly* what is needed. "
    "6. After executing a function and receiving its result, ALWAYS provide a final textual response to the user. "
    "7. If the user asks a simple non-financial question (like 'hello', 'how are you'), respond appropriately and casually without trying to call a financial tool."
)

def handle_ai_query(user_id: int, query_text: str) -> str:
    """
    Processes a user's chat query using the Gemini model, handling tool calls.
    """
    # Check if AI is enabled via app configuration
    if not current_app.config.get('AI_ENABLED'):
        logging.warning("AI Assistant is disabled by configuration.")
        return "AI Assistant is not available: API key not configured."

    try:
        # The genai.configure(api_key=...) was done in __init__.py
        # We just need to instantiate the model here.
        model_init_args = {
            'model_name': 'gemini-1.5-flash-latest',
            'system_instruction': SYSTEM_INSTRUCTION,
        }
        # Only add safety settings if they were successfully configured
        if SAFETY_SETTINGS:
             model_init_args['safety_settings'] = SAFETY_SETTINGS

        model = genai.GenerativeModel(**model_init_args)

        # Define the mapping from tool names (as declared to the AI) to the actual functions
        available_functions = {
            'get_exchange_rate': get_exchange_rate,
            # Use lambda to pass user_id to functions that require it
            'add_transaction': lambda **args_inner: add_transaction(user_id=user_id, **args_inner),
            'get_financial_summary': lambda **args_inner: get_total_by_type(user_id=user_id, **args_inner),
            'generate_pdf_report': lambda: generate_pdf_report(user_id=user_id), # Pass user_id
            'get_current_datetime': get_current_datetime # Does not require user_id
        }

        # Get or create chat history for this user
        # Store chat history in a dictionary keyed by user_id
        if not hasattr(handle_ai_query, 'chat_histories'):
            handle_ai_query.chat_histories = {}
        
        # Get existing chat or create new one
        if user_id not in handle_ai_query.chat_histories:
            handle_ai_query.chat_histories[user_id] = model.start_chat(history=[])
        
        chat = handle_ai_query.chat_histories[user_id]

        logging.info(f"User {user_id} query sent to Gemini: {query_text}")

        # Step 1: Send the user query to the model for analysis and potential tool call
        try:
            # First get current datetime to help with date calculations
            current_datetime = get_current_datetime()
            logging.info(f"Current datetime for user {user_id}: {current_datetime}")
            
            # Send the query with tools
            response = chat.send_message(
                query_text,
                tools=[{'function_declarations': TOOL_DECLARATIONS}],
                generation_config={
                    'temperature': 0.1,  # Lower temperature for more precise responses
                    'top_p': 0.8,
                    'top_k': 40
                }
            )
            
            # Check for empty or invalid response
            if not response or not response.parts:
                logging.warning(f"Gemini response has no parts or is empty. Response: {response}")
                if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason != 0:
                    logging.error(f"Gemini blocked prompt: {response.prompt_feedback}")
                    return "I'm sorry, I cannot process that request due to safety concerns."
                if response and (not hasattr(response, 'candidates') or not response.candidates or not hasattr(response.candidates[0], 'content') or not response.candidates[0].content.parts):
                    logging.error("Gemini response has candidates but no content parts.")
                    return "I received an empty response from the AI. Could you please try again or rephrase?"
                return "I couldn't get a valid response from the AI. Please try again."

            final_text = ""
            tool_calls = []

            # Process the model's initial response
            for part in response.parts:
                if part.function_call:
                    tool_calls.append(part.function_call)
                # Only accumulate text parts that are not tool code
                if hasattr(part, 'text') and part.text and not part.text.strip().startswith('```tool_code'):
                    final_text += part.text

            # Step 2: If tool calls are present, execute them
            if tool_calls:
                tool_responses = []
                for fc in tool_calls:
                    func_name = fc.name
                    args = {key: value for key, value in fc.args.items()}
                    logging.info(f"AI requested function call: {func_name} with args: {args} for user {user_id}")

                    if func_name in available_functions:
                        try:
                            # Execute the function using the mapping
                            function_result = available_functions[func_name](**args)
                            logging.info(f"Function {func_name} execution result: {function_result} for user {user_id}")

                            # Prepare the tool response for the model
                            tool_response_content = {"result": function_result}

                            # Special handling for PDF generation response
                            if func_name == 'generate_pdf_report' and isinstance(function_result, str):
                                tool_response_content = {"result": f"PDF report generated successfully. Filename: {function_result}"}

                            tool_responses.append({
                                "function_response": {
                                    "name": func_name,
                                    "response": tool_response_content
                                }
                            })

                        except Exception as e:
                            logging.error(f"Error executing function {func_name} locally for user {user_id}: {str(e)}", exc_info=True)
                            tool_responses.append({
                                "function_response": {
                                    "name": func_name,
                                    "response": {"error": f"Execution error: {str(e)}"}
                                }
                            })
                    else:
                        logging.error(f"Unknown function requested by AI for user {user_id}: {func_name}")
                        tool_responses.append({
                            "function_response": {
                                "name": func_name,
                                "response": {"error": f"Unknown function: {func_name}"}
                            }
                        })

                # Step 3: Send the tool results back to the model for the final response
                if tool_responses:
                    logging.info(f"Sending tool responses back to AI for user {user_id}: {tool_responses}")
                    try:
                        response = chat.send_message(
                            tool_responses,
                            generation_config={
                                'temperature': 0.1,  # Lower temperature for more precise responses
                                'top_p': 0.8,
                                'top_k': 40
                            }
                        )
                        final_text = ""
                        if response and response.parts:
                            for part in response.parts:
                                if hasattr(part, 'text') and part.text and not part.text.strip().startswith('```tool_code'):
                                    final_text += part.text
                        else:
                            logging.warning(f"AI response after tool execution has no parts or is empty for user {user_id}. Response: {response}")
                            if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason != 0:
                                return "I'm sorry, I cannot provide a summary for that due to safety concerns after the action."
                            final_text = "I executed the requested action, but I couldn't formulate a summary. Please check the relevant dashboard sections."

                    except google.api_core.exceptions.GoogleAPIError as e:
                        logging.error(f"Google API Error after tool execution during send_message for user {user_id}: {str(e)}", exc_info=True)
                        if isinstance(e, google.api_core.exceptions.ResourceExhausted):
                            return "AI Assistant Error: My capabilities are currently exhausted. Please try again in a few minutes."
                        return f"An API error occurred while formulating the response after the action: {str(e)}"
                    except Exception as e:
                        logging.error(f"Unexpected error after tool execution during send_message for user {user_id}: {str(e)}", exc_info=True)
                        final_text = f"An unexpected error occurred after executing the requested functions: {str(e)}"

            # Step 4: Return the final text response to the user
            if not final_text: # Fallback if AI gives no text response at any stage, even after tool calls
                logging.warning(f"AI final response text is empty for user {user_id}. Tool calls attempted: {len(tool_calls)}")
                if tool_calls: # If tools were attempted but no final text was generated after
                    executed_func_names = ", ".join([tc['function_response']['name'] for tc in tool_responses if 'function_response' in tc])
                    final_text = f"I attempted to execute the requested actions ({executed_func_names}), but I couldn't formulate a detailed summary. Please check the relevant dashboard sections."
                elif query_text.strip().lower() in ["hey", "hi", "hello", "how are you", "what's up"]: # Simple greetings
                    final_text = "Hello! I'm your financial assistant. How can I help you today?"
                else: # Generic fallback for unhandled queries
                    final_text = "I received your message, but I'm not sure how to help with that. Could you please rephrase or ask a specific financial question?"

            logging.info(f"Final AI response to user {user_id}: {final_text}")
            return final_text

        except google.api_core.exceptions.GoogleAPIError as e:
            logging.error(f"Google API Error during send_message: {str(e)}", exc_info=True)
            if isinstance(e, google.api_core.exceptions.ResourceExhausted):
                return "AI Assistant Error: My capabilities are currently exhausted. Please try again in a few minutes."
            if isinstance(e, google.api_core.exceptions.PermissionDenied) or isinstance(e, google.api_core.exceptions.Unauthenticated):
                return "AI Assistant Error: There seems to be an issue with the API key or permissions."
            if isinstance(e, google.api_core.exceptions.InvalidArgument):
                return f"AI Assistant Error: Invalid arguments provided to the AI model. Details: {str(e)}"
            return f"An API error occurred while processing your request: {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error during initial send_message: {str(e)}", exc_info=True)
            return f"An unexpected error occurred: {str(e)}"

    except Exception as e:
        # Catch any remaining unexpected errors during the overall process
        logging.error(f"General AI Query handling error for user {user_id}: {str(e)}", exc_info=True)
        # Provide a generic error message to the user
        return "An unexpected error occurred while processing your request with the AI assistant."