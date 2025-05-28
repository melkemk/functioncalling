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
git clone <repository-url>
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
```

## Running the Application

1. Initialize the database:
```bash
flask db init
flask db migrate
flask db upgrade
```

2. Start the Flask development server:
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## Usage

1. Access the dashboard at `/` to view your financial overview
2. Use the chat interface at `/chat` to ask questions about your finances
3. Download reports in PDF or CSV format from the dashboard

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

### Project Structure
```
financial_assistant/
├── backend/
│   ├── app.py              # Main application file
│   ├── requirements.txt    # Python dependencies
│   ├── templates/          # HTML templates
│   │   ├── dashboard.html  # Dashboard template
│   │   └── chat.html      # Chat interface template
│   └── README.md          # This file
```

### Adding New Features
1. Create new database models in `app.py`
2. Add corresponding routes and templates
3. Update the AI assistant's function calling capabilities as needed

## Security Notes

- Never commit your `.env` file or expose API keys
- Use proper authentication in production
- Implement rate limiting for API endpoints
- Use HTTPS in production

## License

This project is licensed under the MIT License - see the LICENSE file for details. 