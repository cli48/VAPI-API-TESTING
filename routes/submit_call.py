# routes/submit_call.py
import os
from flask import Blueprint, request, jsonify, current_app
from psycopg.types.json import Jsonb

from db import get_db_connection

submit_call_bp = Blueprint("submit_call", __name__)

@submit_call_bp.route("/submit_call", methods=["POST"])
def submit_call():
    """
    Vapi end-of-call-report webhook.

    Expects a body like the sample you captured from Postman:
    {
      "message": {
        "type": "end-of-call-report",
        "analysis": {
          "summary": "...",
          "structuredData": {
            "phone_number": "+10000000000",
            "direction": "inbound",
            "first_name": "Calvin",
            "summary": "User Calvin ...",
            "metadata": { "ended_reason": "assistant-ended-call" },
            "purpose": "unclear",
            "action": "none"
          },
          ...
        },
        "startedAt": "...",
        "endedAt": "...",
        "endedReason": "assistant-ended-call",
        "summary": "...",
        "transcript": "...",
        "recordingUrl": "...",
        "call": { "id": "..." },
        ...
      }
    }
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
        return jsonify({"error": "Invalid API key"}), 403

    # 2) Parse JSON
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON"}), 400

    message = data.get("message") or {}
    msg_type = message.get("type")

    # Only handle end-of-call-report
    if msg_type != "end-of-call-report":
        current_app.logger.info(f"/submit_call: ignoring message.type=%r", msg_type)
        return jsonify({"status": "ignored", "reason": f"message.type={msg_type}"}), 200

    # 3) Extract fields from analysis.structuredData
    analysis = message.get("analysis") or {}
    structured = analysis.get("structuredData") or {}

    phone_number = structured.get("phone_number")
    direction = structured.get("direction")
    first_name = structured.get("first_name")
    purpose = structured.get("purpose")
    action = structured.get("action")
    metadata = structured.get("metadata") or {}

    # Prefer structured summary, fall back to top-level summary
    summary = structured.get("summary") or message.get("summary")

    # 4) Extract other call-level fields
    call = message.get("call") or {}
    vapi_call_id = call.get("id")

    call_started = message.get("startedAt")
    call_ended = message.get("endedAt")
    ended_reason = message.get("endedReason")

    transcript = message.get("transcript")
    recording_url = message.get("recordingUrl")

    # Basic sanity log
    current_app.logger.info(
        "Saving call: vapi_call_id=%s phone=%s direction=%s",
        vapi_call_id,
        phone_number,
        direction,
    )

    # 5) Insert into DB
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calls (
                        vapi_call_id,
                        phone_number,
                        direction,
                        first_name,
                        purpose,
                        action,
                        summary,
                        transcript,
                        recording_url,
                        ended_reason,
                        metadata,
                        call_started,
                        call_ended
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (vapi_call_id) DO UPDATE
                    SET
                        phone_number   = EXCLUDED.phone_number,
                        direction      = EXCLUDED.direction,
                        first_name     = EXCLUDED.first_name,
                        purpose        = EXCLUDED.purpose,
                        action         = EXCLUDED.action,
                        summary        = EXCLUDED.summary,
                        transcript     = EXCLUDED.transcript,
                        recording_url  = EXCLUDED.recording_url,
                        ended_reason   = EXCLUDED.ended_reason,
                        metadata       = EXCLUDED.metadata,
                        call_started   = EXCLUDED.call_started,
                        call_ended     = EXCLUDED.call_ended
                    """,
                    (
                        vapi_call_id,
                        phone_number,
                        direction,
                        first_name,
                        purpose,
                        action,
                        summary,
                        transcript,
                        recording_url,
                        ended_reason,
                        Jsonb(metadata),
                        call_started,
                        call_ended,
                    ),
                )
    except Exception as e:
        current_app.logger.exception("Error saving call from Vapi")
        return jsonify({"error": "Database error"}), 500

    return jsonify({"status": "ok"}), 200
