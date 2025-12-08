# routes/submit_call.py
import os
import json
from flask import Blueprint, request, jsonify
from psycopg.types.json import Jsonb  # psycopg3 JSONB wrapper

from db import get_db_connection

submit_call_bp = Blueprint("submit_call", __name__)

# Adjust these to match what your agent actually uses
VALID_PURPOSES = {"booking", "reschedule", "cancel", "pricing", "general"}
VALID_ACTIONS = {"created_booking", "rescheduled", "cancelled", "none"}


@submit_call_bp.route("/submit_call", methods=["POST"])
def submit_call():
    """
    Endpoint for Vapi AI agent to log call data.
    Secured with a Bearer API key.
    Expects Vapi tool payload:
      body.message.toolCallList[0].function.arguments
    """

    # 1) API key auth -----------------------------------------
    expected_key = os.environ.get("API_KEY_SECRET")
    auth_header = request.headers.get("Authorization")

    if not expected_key:
        return jsonify({"error": "Server missing API_KEY_SECRET"}), 500

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing Authorization header"}), 401

    token = auth_header.replace("Bearer ", "").strip()
    if token != expected_key:
        return jsonify({"error": "Invalid API key"}), 403

    # 2) Parse Vapi payload ------------------------------------
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    try:
        tool_call = payload["message"]["toolCallList"][0]
        tool_call_id = tool_call["id"]
        raw_args = tool_call["function"]["arguments"]
    except (KeyError, IndexError, TypeError):
        return jsonify({"error": "Malformed Vapi tool payload"}), 400

    # arguments might be an object or a JSON string
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            return jsonify({"error": "Could not parse tool arguments JSON"}), 400
    else:
        args = raw_args or {}

    # 3) Extract fields from arguments -------------------------
    phone_number = args.get("phone_number")
    direction = args.get("direction")          # "inbound" / "outbound"
    purpose = args.get("purpose")              # should be in VALID_PURPOSES
    action = args.get("action")                # should be in VALID_ACTIONS
    summary = args.get("summary")
    transcript = args.get("transcript")
    metadata = args.get("metadata") or {}      # free-form JSON (dict)

    # Optional timestamps / duration if you send them
    started_at = args.get("started_at")        # ISO 8601 string or None
    ended_at = args.get("ended_at")
    duration_seconds = args.get("duration_seconds")

    # 4) Basic validation --------------------------------------
    if not phone_number:
        return jsonify({"error": "phone_number is required"}), 400

    if purpose and purpose not in VALID_PURPOSES:
        return jsonify(
            {"error": f"Invalid purpose '{purpose}'. Must be one of {sorted(VALID_PURPOSES)}"}
        ), 400

    if action and action not in VALID_ACTIONS:
        return jsonify(
            {"error": f"Invalid action '{action}'. Must be one of {sorted(VALID_ACTIONS)}"}
        ), 400

    # 5) Insert into Postgres ----------------------------------
    conn = get_db_connection()

    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calls
                        (phone_number,
                         direction,
                         purpose,
                         action,
                         metadata,
                         summary,
                         transcript,
                         started_at,
                         ended_at,
                         duration_seconds)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        phone_number,
                        direction,
                        purpose,
                        action,
                        Jsonb(metadata),
                        summary,
                        transcript,
                        started_at,
                        ended_at,
                        duration_seconds,
                    ),
                )
                call_id = cur.fetchone()[0]

    except Exception as e:
        # Log e in real app
        return jsonify({"error": "Database insert failed", "details": str(e)}), 500
    finally:
        conn.close()

    # 6) Respond in Vapi's expected format ---------------------
    return jsonify(
        {
            "results": [
                {
                    "toolCallId": tool_call_id,
                    "result": {
                        "status": "ok",
                        "call_id": call_id,
                        "phone_number": phone_number,
                    },
                }
            ]
        }
    ), 200
