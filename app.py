from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

@app.route("/vapi-webhook", methods=["POST"])
def vapi_webhook():
    event = request.get_json(force=True, silent=True) or {}

    # Just log what you got for now
    print("Received from VAPI:", event, flush=True)

    # ---- SIMPLE ECHO EXAMPLE (for a 'tool' style webhook) ----
    # If this endpoint is used as a VAPI Function Tool webhook,
    # VAPI will send something like:
    # {
    #   "toolCallId": "abc123",
    #   "args": { ... tool arguments ... }
    # }
    tool_call_id = event.get("toolCallId")
    args = event.get("args", {})

    # Do your logic here. For now, just echo back something.
    result = {
        "message": f"Hello from Flask! You passed: {args}"
    }

    # VAPI expects a "results" array with toolCallId + result :contentReference[oaicite:0]{index=0}
    if tool_call_id:
        return jsonify({
            "results": [
                {
                    "toolCallId": tool_call_id,
                    "result": result
                }
            ]
        })

    # If it wasn't a tool call, just ACK it
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=5000, debug=True)
