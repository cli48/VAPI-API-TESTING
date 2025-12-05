# app.py
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# Import blueprints
from routes.health import health_bp
from routes.submit_call import submit_call_bp
from routes.contacts import contacts_bp 

def create_app():
    app = Flask(__name__)

    # Register all endpoints
    app.register_blueprint(health_bp)
    app.register_blueprint(submit_call_bp)
    app.register_blueprint(contacts_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
