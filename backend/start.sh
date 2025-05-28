#!/bin/bash

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start Gunicorn
gunicorn -c gunicorn_config.py run:app 