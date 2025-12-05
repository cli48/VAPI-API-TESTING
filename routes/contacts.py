# routes/contacts.py
import os
from flask import Blueprint, request, jsonify

from db import get_db_connection

contacts_bp = Blueprint("contacts", __name__)


@contacts_bp.route("/contacts", methods=["POST"])
def upsert_contact():
    """
    Add or update a contact.

    Auth: Bearer API key in Authorization header.

    Expected JSON:
    {
      "phone_number": "+17035551234",     # required
      "first_name": "Calvin",             # optional
      "last_name": "Li",                  # optional
      "email": "calvin@example.com"       # optional
    }
    """

    expected_key = os.environ.get("API_KEY_SECRET")
    auth_header = request.headers.get("Authorization")

    if not expected_key:
        return jsonify({"error": "Server missing API_KEY_SECRET"}), 500

    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing Authorization header"}), 401

    token = auth_header.replace("Bearer ", "").strip()
    if token != expected_key:
        return jsonify({"error": "Invalid API key"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    phone_number = data.get("phone_number")
    if not phone_number:
        return jsonify({"error": "Missing required field: phone_number"}), 400

    first_name = data.get("first_name")
    last_name = data.get("last_name")
    email = data.get("email")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO contacts (phone_number, first_name, last_name, email)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (phone_number)
            DO UPDATE SET
                first_name = COALESCE(contacts.first_name, EXCLUDED.first_name),
                last_name  = COALESCE(contacts.last_name,  EXCLUDED.last_name),
                email      = COALESCE(contacts.email,      EXCLUDED.email)
            RETURNING id, phone_number, first_name, last_name, email;
            """,
            (phone_number, first_name, last_name, email),
        )

        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        # dict_row from db.py will make 'row' a dict
        if isinstance(row, dict):
            contact = {
                "id": row["id"],
                "phone_number": row["phone_number"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "email": row["email"],
            }
        else:
            contact = {
                "id": row[0],
                "phone_number": row[1],
                "first_name": row[2],
                "last_name": row[3],
                "email": row[4],
            }

        return jsonify({
            "status": "success",
            "contact": contact
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
