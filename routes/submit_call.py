# routes/submit_call.py
import os
from flask import Blueprint, request, jsonify
from psycopg.types.json import Jsonb  # NEW: psycopg3 JSONB wrapper

from db import get_db_connection

submit_call_bp = Blueprint("submit_call", __name__)

VALID_PURPOSES = {"booking", "reschedule", "cancel", "pricing", "general"}
VALID_ACTIONS = {"created_booking", "rescheduled", "cancelled", "none"}


@submit_call_bp.route("/submit_call", methods=["POST"])
def submit_call():
    """
    Endpoint for VAPI AI agent to log call data.
    Secured with a Bearer API key.
    """

    # 1) API key auth
    expected_key = os.environ.get("API_KEY_SECRET")
    auth_header = request.headers.get("Authorization")

    if not expected_key:
        return jsonify({"error": "Server missing API_KEY_SECRET"}), 500

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing Authorization header"}), 401

    token = auth_header.replace("Bearer ", "").strip()
    if token != expected_key:
        return jsonify({"error": "Invalid API key"}), 401

    # 2) Parse JSON
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    required = ["phone_number", "direction"]
    missing = [f for f in required if f not in data]

    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    phone_number = data["phone_number"]
    direction = data["direction"]
    first_name = data.get("first_name")
    summary = data.get("summary")
    metadata = data.get("metadata") or {}

    purpose = data.get("purpose", "general")
    action = data.get("action", "none")

    if purpose not in VALID_PURPOSES:
        return jsonify({"error": f"Invalid purpose '{purpose}'"}), 400
    if action not in VALID_ACTIONS:
        return jsonify({"error": f"Invalid action '{action}'"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Upsert contact
        cur.execute(
            """
            INSERT INTO contacts (phone_number, first_name)
            VALUES (%s, %s)
            ON CONFLICT (phone_number)
            DO UPDATE SET first_name =
                COALESCE(EXCLUDED.first_name, contacts.first_name)
            RETURNING id;
            """,
            (phone_number, first_name),
        )
        contact_row = cur.fetchone()
        contact_id = contact_row["id"] if isinstance(contact_row, dict) else contact_row[0]

        # Insert call
        cur.execute(
            """
            INSERT INTO calls
                (phone_number, direction, summary, metadata, purpose, action)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (phone_number, direction, summary, Jsonb(metadata), purpose, action),
        )
        call_row = cur.fetchone()
        call_id = call_row["id"] if isinstance(call_row, dict) else call_row[0]

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "status": "success",
            "contact_id": contact_id,
            "call_id": call_id
        }), 201

    except Exception as e:
        # In production you’d log this instead of returning raw error
        return jsonify({"error": str(e)}), 500
