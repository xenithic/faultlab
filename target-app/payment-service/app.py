import os
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "payment-service",
        "description": "FaultLab Target Application - Payment Service",
        "version": "0.1.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "payment-service"
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5004))
    app.run(host="0.0.0.0", port=port)
