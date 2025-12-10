# routes/submit_call.py
import os
from flask import Blueprint, request, jsonify, current_app

from db import get_db_connection

submit_call_bp = Blueprint("submit_call", __name__)


def extract_call_fields(payload: dict) -> dict:
    """
    Extract minimal fields for contacts + calls from Vapi end-of-call-report payload.
    """
    msg = payload.get("message", {}) or {}

    call_obj = msg.get("call", {}) or {}
    customer = msg.get("customer", {}) or {}
    analysis = msg.get("analysis", {}) or {}
    structured = analysis.get("structuredData", {}) or {}

    # Direction: inbound / outbound / unknown
    call_type = (call_obj.get("type") or "").lower()
    if "inbound" in call_type:
        direction = "inbound"
    elif "outbound" in call_type:
        direction = "outbound"
    else:
        direction = "unknown"

    # Duration as int if present
    duration_raw = msg.get("durationSeconds")
    if isinstance(duration_raw, (int, float)):
        duration_sec = int(round(duration_raw))
    else:
        duration_sec = None

    # Summary(s)
    summary = analysis.get("summary") or msg.get("summary")
    short_summary = structured.get("callSummary")

    # Cost
    cost_breakdown = msg.get("costBreakdown", {}) or {}
    cost_total = cost_breakdown.get("total", msg.get("cost"))

    return {
        # foreign key into contacts
        "phone_number": customer.get("number"),

        # pointer back to Vapi
        "vapi_call_id": call_obj.get("id"),

        # basic call info
        "direction": direction,
        "started_at": msg.get("startedAt"),
        "ended_at": msg.get("endedAt"),
        "duration_sec": duration_sec,
        "ended_reason": msg.get("endedReason"),

        # human readable
        "summary": summary,
        "short_summary": short_summary,

        # links
        "recording_url": msg.get("recordingUrl"),
        "log_url": msg.get("logUrl"),

        # cost
        "cost_total": cost_total,
    }


@submit_call_bp.route("/submit_call", methods=["POST"])
def submit_call():
    """
    Vapi webhook for end-of-call-report.

    - Validates API_KEY_SECRET
    - Accepts the full end-of-call-report payload
    - Extracts minimal fields
    - Upserts into contacts
    - Inserts into calls (idempotent on vapi_call_id)
    """

    # 1) API key auth for this webhook
    expected_key = os.environ.get("API_KEY_SECRET")
    auth_header = request.headers.get("Authorization", "")

    if not expected_key:
        current_app.logger.error("API_KEY_SECRET is not set on server")
        return jsonify({"error": "Server misconfiguration"}), 500

    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing Authorization header"}), 401

    token = auth_header.replace("Bearer ", "").strip()
    if token != expected_key:
        return jsonify({"error": "Invalid API key"}), 403

    # 2) Parse JSON payload
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Invalid or missing JSON"}), 400

    message = payload.get("message") or {}
    if message.get("type") != "end-of-call-report":
        # Ignore other message types (tool-calls, etc.)
        return jsonify({"status": "ignored", "reason": "not end-of-call-report"}), 200

    # 3) Extract fields
    data = extract_call_fields(payload)
    phone_number = data["phone_number"]
    vapi_call_id = data["vapi_call_id"]

    if not phone_number or not vapi_call_id:
        current_app.logger.warning(
            "submit_call: missing phone_number or vapi_call_id in payload"
        )
        return jsonify({"error": "Missing phone_number or vapi_call_id"}), 400

    # 4) DB insert: contacts + calls
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                # Upsert contact (minimal)
                cur.execute(
                    """
                    INSERT INTO contacts (phone_number)
                    VALUES (%s)
                    ON CONFLICT (phone_number) DO NOTHING;
                    """,
                    (phone_number,),
                )

                # Insert call row, idempotent on vapi_call_id
                cur.execute(
                    """
                    INSERT INTO calls (
                        vapi_call_id,
                        phone_number,
                        direction,
                        started_at,
                        ended_at,
                        duration_sec,
                        ended_reason,
                        summary,
                        short_summary,
                        recording_url,
                        log_url,
                        cost_total
                    )
                    VALUES (
                        %(vapi_call_id)s,
                        %(phone_number)s,
                        %(direction)s,
                        %(started_at)s,
                        %(ended_at)s,
                        %(duration_sec)s,
                        %(ended_reason)s,
                        %(summary)s,
                        %(short_summary)s,
                        %(recording_url)s,
                        %(log_url)s,
                        %(cost_total)s
                    )
                    ON CONFLICT (vapi_call_id) DO NOTHING;
                    """,
                    data,
                )

    except Exception as e:
        current_app.logger.exception("submit_call: database error")
        return jsonify({"error": "Database error", "detail": str(e)}), 500

    current_app.logger.info(
        "submit_call: stored call vapi_call_id=%s phone=%s", vapi_call_id, phone_number
    )

    return jsonify(
        {
            "status": "ok",
            "vapi_call_id": vapi_call_id,
            "phone_number": phone_number,
        }
    ), 200
