# app/routes/__init__.py
# This file is used to register blueprints with the Flask app instance

from .main_routes import main as main_blueprint
from .api_routes import api as api_blueprint

def register_routes(app):
    """Registers all blueprints with the Flask application."""
    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint)
    # Register other blueprints here if you add them