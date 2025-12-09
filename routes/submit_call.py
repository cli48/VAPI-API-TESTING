# routes/submit_call.py
import os
from flask import Blueprint, request, jsonify, current_app
from psycopg.types.json import Jsonb

from db import get_db_connection

submit_call_bp = Blueprint("submit_call", __name__)


@submit_call_bp.route("/submit_call", methods=["POST"])
def submit_call():
    """
    Vapi webhook for call/tool events.

    Example payload (truncated):

    {
      "message": {
        "timestamp": 1765255007055,
        "type": "tool-calls",
        "toolCalls": [...],
        "artifact": {...},
        "call": {
          "id": "019b0165-a031-7aa3-a6e7-17b6e1105112",
          "orgId": "b4d50daf-...",
          "type": "inboundPhoneCall",
          "createdAt": "...",
          "updatedAt": "...",
          "cost": 0,
          "transport": { ... },
          "phoneCallProvider": "vapi",
          "phoneCallProviderId": "...",
          "phoneCallTransport": "sip",
          ...
        },
        "phoneNumber": { ... },
        "customer": { ... },
        "assistant": { ... },
        ...
      }
    }

    We map the important fields into the Calls1 table and keep
    the rest in JSONB for future-proofing.
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

    # 3) Extract core objects
    call_obj = message.get("call") or {}
    phone_number_obj = message.get("phoneNumber") or {}
    customer_obj = message.get("customer") or {}
    assistant_obj = message.get("assistant") or {}
    artifact_obj = message.get("artifact") or {}

    tool_calls = message.get("toolCalls") or []
    tool_call_list = message.get("toolCallList") or []
    tool_with_tool_call_list = message.get("toolWithToolCallList") or []

    # 4) Primary ID (Calls1.id) from call.id
    call_id = call_obj.get("id")
    if not call_id:
        current_app.logger.warning("submit_call: missing call.id, cannot store event")
        return jsonify({"error": "Missing call.id in payload"}), 400

    org_id = call_obj.get("orgId") or assistant_obj.get("orgId") or message.get("orgId")

    # Event-level info
    event_timestamp_ms = message.get("timestamp")
    event_type = msg_type

    # Call-level info
    call_type = call_obj.get("type")
    call_status = call_obj.get("status")
    call_cost = call_obj.get("cost")
    call_created_at = call_obj.get("createdAt")
    call_updated_at = call_obj.get("updatedAt")

    transport = call_obj.get("transport") or {}
    conversation_type = transport.get("conversationType")
    transport_provider = transport.get("provider")

    phone_call_provider = call_obj.get("phoneCallProvider")
    phone_call_transport = call_obj.get("phoneCallTransport")
    phone_call_provider_id = call_obj.get("phoneCallProviderId")

    # Customer info
    # Prefer top-level customer, fall back to call.customer if needed
    if not customer_obj:
        customer_obj = call_obj.get("customer") or {}

    customer_number = customer_obj.get("number")
    customer_sip_uri = customer_obj.get("sipUri")

    # Phone number info
    # phoneNumberId appears on both top-level and call; prefer top-level
    phone_number_id = message.get("phoneNumberId") or phone_number_obj.get("id") or call_obj.get("phoneNumberId")
    phone_number = phone_number_obj.get("number")
    phone_number_name = phone_number_obj.get("name")

    # Assistant info
    assistant_id = assistant_obj.get("id")
    assistant_org_id = assistant_obj.get("orgId")
    assistant_name = assistant_obj.get("name")

    model_obj = assistant_obj.get("model") or {}
    assistant_model = model_obj.get("model")
    assistant_model_provider = model_obj.get("provider")

    voice_obj = assistant_obj.get("voice") or {}
    assistant_voice_id = voice_obj.get("voiceId")
    assistant_voice_provider = voice_obj.get("provider")

    # 5) Extract last user / assistant messages from artifact.messages (if present)
    last_user_message = None
    last_assistant_message = None

    artifact_messages = artifact_obj.get("messages") or []
    if isinstance(artifact_messages, list):
        # Walk backwards to find the last user and assistant messages
        for m in reversed(artifact_messages):
            role = m.get("role")
            msg_text = m.get("message")
            if role == "user" and last_user_message is None:
                last_user_message = msg_text
            if role in ("bot", "assistant") and last_assistant_message is None:
                last_assistant_message = msg_text
            if last_user_message is not None and last_assistant_message is not None:
                break

    current_app.logger.info(
        "submit_call: saving Calls1 row id=%s event_type=%s customer=%s",
        call_id,
        event_type,
        customer_number,
    )

    # 6) Insert into Calls1
    conn = get_db_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO Calls1 (
                        id,
                        org_id,
                        event_timestamp_ms,
                        event_type,
                        call_type,
                        call_status,
                        call_cost,
                        call_created_at,
                        call_updated_at,
                        conversation_type,
                        transport_provider,
                        phone_call_provider,
                        phone_call_transport,
                        phone_call_provider_id,
                        customer_number,
                        customer_sip_uri,
                        phone_number_id,
                        phone_number,
                        phone_number_name,
                        assistant_id,
                        assistant_org_id,
                        assistant_name,
                        assistant_model,
                        assistant_model_provider,
                        assistant_voice_id,
                        assistant_voice_provider,
                        last_user_message,
                        last_assistant_message,
                        tool_calls_json,
                        tool_call_list_json,
                        tool_with_tool_call_list_json,
                        artifact_json,
                        call_json,
                        phone_number_json,
                        customer_json,
                        assistant_json,
                        raw_payload
                    )
                    VALUES (
                        %(id)s,
                        %(org_id)s,
                        %(event_timestamp_ms)s,
                        %(event_type)s,
                        %(call_type)s,
                        %(call_status)s,
                        %(call_cost)s,
                        %(call_created_at)s,
                        %(call_updated_at)s,
                        %(conversation_type)s,
                        %(transport_provider)s,
                        %(phone_call_provider)s,
                        %(phone_call_transport)s,
                        %(phone_call_provider_id)s,
                        %(customer_number)s,
                        %(customer_sip_uri)s,
                        %(phone_number_id)s,
                        %(phone_number)s,
                        %(phone_number_name)s,
                        %(assistant_id)s,
                        %(assistant_org_id)s,
                        %(assistant_name)s,
                        %(assistant_model)s,
                        %(assistant_model_provider)s,
                        %(assistant_voice_id)s,
                        %(assistant_voice_provider)s,
                        %(last_user_message)s,
                        %(last_assistant_message)s,
                        %(tool_calls_json)s,
                        %(tool_call_list_json)s,
                        %(tool_with_tool_call_list_json)s,
                        %(artifact_json)s,
                        %(call_json)s,
                        %(phone_number_json)s,
                        %(customer_json)s,
                        %(assistant_json)s,
                        %(raw_payload)s
                    )
                    ON CONFLICT (id) DO UPDATE
                    SET
                        org_id                   = EXCLUDED.org_id,
                        event_timestamp_ms       = EXCLUDED.event_timestamp_ms,
                        event_type               = EXCLUDED.event_type,
                        call_type                = EXCLUDED.call_type,
                        call_status              = EXCLUDED.call_status,
                        call_cost                = EXCLUDED.call_cost,
                        call_created_at          = EXCLUDED.call_created_at,
                        call_updated_at          = EXCLUDED.call_updated_at,
                        conversation_type        = EXCLUDED.conversation_type,
                        transport_provider       = EXCLUDED.transport_provider,
                        phone_call_provider      = EXCLUDED.phone_call_provider,
                        phone_call_transport     = EXCLUDED.phone_call_transport,
                        phone_call_provider_id   = EXCLUDED.phone_call_provider_id,
                        customer_number          = EXCLUDED.customer_number,
                        customer_sip_uri         = EXCLUDED.customer_sip_uri,
                        phone_number_id          = EXCLUDED.phone_number_id,
                        phone_number             = EXCLUDED.phone_number,
                        phone_number_name        = EXCLUDED.phone_number_name,
                        assistant_id             = EXCLUDED.assistant_id,
                        assistant_org_id         = EXCLUDED.assistant_org_id,
                        assistant_name           = EXCLUDED.assistant_name,
                        assistant_model          = EXCLUDED.assistant_model,
                        assistant_model_provider = EXCLUDED.assistant_model_provider,
                        assistant_voice_id       = EXCLUDED.assistant_voice_id,
                        assistant_voice_provider = EXCLUDED.assistant_voice_provider,
                        last_user_message        = EXCLUDED.last_user_message,
                        last_assistant_message   = EXCLUDED.last_assistant_message,
                        tool_calls_json          = EXCLUDED.tool_calls_json,
                        tool_call_list_json      = EXCLUDED.tool_call_list_json,
                        tool_with_tool_call_list_json = EXCLUDED.tool_with_tool_call_list_json,
                        artifact_json            = EXCLUDED.artifact_json,
                        call_json                = EXCLUDED.call_json,
                        phone_number_json        = EXCLUDED.phone_number_json,
                        customer_json            = EXCLUDED.customer_json,
                        assistant_json           = EXCLUDED.assistant_json,
                        raw_payload              = EXCLUDED.raw_payload,
                        updated_at               = NOW()
                    """,
                    {
                        "id": call_id,
                        "org_id": org_id,
                        "event_timestamp_ms": event_timestamp_ms,
                        "event_type": event_type,
                        "call_type": call_type,
                        "call_status": call_status,
                        "call_cost": call_cost,
                        "call_created_at": call_created_at,
                        "call_updated_at": call_updated_at,
                        "conversation_type": conversation_type,
                        "transport_provider": transport_provider,
                        "phone_call_provider": phone_call_provider,
                        "phone_call_transport": phone_call_transport,
                        "phone_call_provider_id": phone_call_provider_id,
                        "customer_number": customer_number,
                        "customer_sip_uri": customer_sip_uri,
                        "phone_number_id": phone_number_id,
                        "phone_number": phone_number,
                        "phone_number_name": phone_number_name,
                        "assistant_id": assistant_id,
                        "assistant_org_id": assistant_org_id,
                        "assistant_name": assistant_name,
                        "assistant_model": assistant_model,
                        "assistant_model_provider": assistant_model_provider,
                        "assistant_voice_id": assistant_voice_id,
                        "assistant_voice_provider": assistant_voice_provider,
                        "last_user_message": last_user_message,
                        "last_assistant_message": last_assistant_message,
                        "tool_calls_json": Jsonb(tool_calls),
                        "tool_call_list_json": Jsonb(tool_call_list),
                        "tool_with_tool_call_list_json": Jsonb(tool_with_tool_call_list),
                        "artifact_json": Jsonb(artifact_obj),
                        "call_json": Jsonb(call_obj),
                        "phone_number_json": Jsonb(phone_number_obj),
                        "customer_json": Jsonb(customer_obj),
                        "assistant_json": Jsonb(assistant_obj),
                        "raw_payload": Jsonb(message),
                    },
                )
    except Exception as e:
        current_app.logger.exception("Error saving Calls1 row from Vapi")
        return jsonify({"error": "Database error"}), 500

    return jsonify({"status": "ok"}), 200
