import os
import json
from flask import Blueprint, request, jsonify
from psycopg.types.json import Jsonb  # if you're using this already

from db import get_db_connection

submit_call_bp = Blueprint("submit_call", __name__)

VALID_PURPOSES = {"booking", "reschedule", "cancel", "pricing", "general"}
VALID_ACTIONS = {"created_booking", "rescheduled", "cancelled", "none"}


@submit_call_bp.route("/submit_call", methods=["POST"])
def submit_call():
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

    # 2) Parse Vapi envelope
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing JSON body"}), 400

    # Debug (TEMPORARY – super helpful right now)
    print("RAW VAPI PAYLOAD:", json.dumps(data, indent=2))

    message = data.get("message") or {}
    tool_calls = message.get("toolCallList") or []
    if not tool_calls:
        return jsonify({"error": "No toolCallList provided"}), 400

    tool_call = tool_calls[0]
    tool_call_id = tool_call.get("id")
    function = tool_call.get("function") or {}
    raw_args = function.get("arguments")

    # 3) arguments may be a JSON string or an object
    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON in function.arguments"}), 400
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        return jsonify({"error": "function.arguments must be object or JSON string"}), 400

    # Debug
    print("EXTRACTED ARGS:", json.dumps(args, indent=2))

    # 4) Extract your actual call fields from args
    call_id = args.get("call_id")
    phone_number = args.get("phone_number")
    direction = args.get("direction")  # inbound / outbound
    purpose = args.get("purpose")
    action_taken = args.get("action_taken")
    summary = args.get("summary")
    started_at = args.get("started_at")
    ended_at = args.get("ended_at")
    transcript = args.get("transcript")
    metadata = args.get("metadata") or {}

    # 5) Basic validation
    missing = [f for f in ["call_id", "phone_number", "direction"] if not args.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    if purpose and purpose not in VALID_PURPOSES:
        return jsonify({"error": f"Invalid purpose: {purpose}"}), 400

    if action_taken and action_taken not in VALID_ACTIONS:
        return jsonify({"error": f"Invalid action_taken: {action_taken}"}), 400

    # 6) Save to database (example – adjust to your schema)
    conn = get_db_connection()
    cur = conn.cursor()

    # Example insert – change columns/table names to match your DB
    cur.execute(
        """
        INSERT INTO calls (
            call_id,
            phone_number,
            direction,
            purpose,
            action_taken,
            summary,
            started_at,
            ended_at,
            transcript,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            call_id,
            phone_number,
            direction,
            purpose,
            action_taken,
            summary,
            started_at,
            ended_at,
            Jsonb(transcript) if transcript is not None else None,
            Jsonb(metadata),
        ),
    )

    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    saved_id = row[0] if row else None

    # 7) Respond in Vapi's expected tool format
    # (this is what your Express example was doing)
    return jsonify({
        "results": [
            {
                "toolCallId": tool_call_id,
                "result": {
                    "status": "ok",
                    "saved_db_id": saved_id,
                    "call_id": call_id,
                },
            }
        ]
    }), 200
