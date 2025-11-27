import os
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Enable CORS so VAPI dashboard tests work (browser-based)
CORS(app)

@app.route("/hello", methods=["GET"])
def hello():
    return jsonify({"message": "Hello World"}), 200

if __name__ == "__main__":
    # Render requires your app to listen on the port it provides
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
