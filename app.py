# app.py
import os
from flask import Flask
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()

def create_app():
    app = Flask(__name__)

    # Enable CORS on the app (all routes)
    CORS(
        app,
        resources={r"/*": {"origins": "*"}},  # allow all origins while testing
        supports_credentials=True,
    )

    # Import blueprints AFTER app is created to avoid circular import issues
    from routes.health import health_bp
    from routes.submit_call import submit_call_bp
    from routes.contacts import contacts_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(submit_call_bp)
    app.register_blueprint(contacts_bp)

    return app


app = create_app()

if __name__ == "__main__":
    # For Render, PORT comes from env; for local you can still use 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
