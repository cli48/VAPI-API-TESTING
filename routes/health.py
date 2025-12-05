# routes/health.py
from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

@health_bp.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@health_bp.route("/hello", methods=["GET"])
def hello():
    """
    Simple hello world route to verify the app is running.
    """
    return jsonify({"message": "Hello World"}), 200
