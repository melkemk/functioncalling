# Financial Assistant Backend

A Flask-based financial management system with AI-powered insights and payment processing capabilities.

## Features

- User and client management
- Income and expense tracking
- Invoice management
- AI-powered financial insights using Google's Gemini API
- Payment processing with Chapa
- PDF and CSV report generation
- Modern, responsive UI with Tailwind CSS

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- SQLite3

## Installation

1. Clone the repository:
```bash
git clone https://github.com/melkemk/functioncalling
cd financial_assistant/backend
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

4. Set up your environment variables:
Create a `.env` file in the project root with the following variables:
```
CHAPA_SECRET_KEY=your-chapa-secret-key
GEMINI_API_KEY=your-gemini-api-key
FLASK_SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///freelancer.db
EXCHANGE_RATE_API_KEY=your-exchange-rate-api-key
```

## Running the Application

1. Initialize the database (if using Flask-Migrate):
```bash
flask db init
flask db migrate
flask db upgrade
```

2. Start the application (development):
```bash
python app.py
```
Or with Gunicorn (production):
```bash
gunicorn app:app
```

The application will be available at `http://localhost:5000` (or `:8000` for Gunicorn).

## Usage

- Access the dashboard at `/` to view your financial overview
- Use the chat interface at `/chat` to ask questions about your finances
- Download reports in PDF or CSV format from the dashboard

## Project Structure

```
financial_assistant/
└── backend/
    ├── app.py                  # Main application file (entry point)
    ├── requirements.txt        # Python dependencies
    ├── README.md               # Project documentation
    ├── app.log                 # Application log file
    ├── error.log               # Error log file
    ├── access.log              # Access log file
    ├── gunicorn_config.py      # Gunicorn configuration (if used)
    ├── run.py                  # Alternate entry point (if used)
    ├── start.sh                # Shell script to start the app (if used)
    ├── instance/
    │   └── freelancer.db       # SQLite database file
    ├── app/
    │   ├── __init__.py
    │   ├── models/
    │   │   ├── user.py         # User model
    │   │   ├── transaction.py  # Transaction model
    │   │   └── chat_history.py # Chat history model
    │   ├── routes/
    │   │   ├── chat_routes.py      # Chat-related routes
    │   │   └── financial_routes.py # Financial data routes
    │   ├── services/
    │   │   ├── ai_service.py       # AI integration logic
    │   │   └── financial_service.py# Financial logic
    │   ├── utils/                  # Utility functions (if any)
    │   ├── static/                 # Static files (CSS, JS, images)
    │   └── templates/
    │       ├── dashboard.html      # Dashboard template
    │       └── chat.html           # Chat interface template
    └── __pycache__/                # Python bytecode cache
```

## API Integration

### Chapa Payment Integration
- Replace `CHAPA_SECRET_KEY` in the `.env` file with your Chapa API key
- The application uses Chapa's API for payment verification and transfers

### Gemini AI Integration
- Replace `GEMINI_API_KEY` in the `.env` file with your Google Gemini API key
- The AI assistant can answer questions about:
  - Total income for a date range
  - Expenses by category
  - Net profit calculations
  - Financial trends and insights

## Development

### Adding New Features
1. Create new database models in `app/models/`
2. Add or update routes in `app/routes/`
3. Add business logic in `app/services/`
4. Update templates in `app/templates/`
5. Update the AI assistant's function calling capabilities as needed

