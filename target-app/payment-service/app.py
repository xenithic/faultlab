import datetime
import os
import uuid
from flask import Flask, jsonify, request

app = Flask(__name__)

# In-memory storage for processed payment transactions
PAYMENTS = {}


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


@app.route("/payments", methods=["POST"])
@app.route("/payments/process", methods=["POST"])
def process_payment():
    """
    Process a simulated payment request.

    Request Contract:
    {
        "order_id": str (required),
        "amount": float > 0 (required),
        "currency": str (optional, default: "USD"),
        "simulate_failure": bool (optional, default: False),
        "simulate_status": str (optional, "success" | "failure")
    }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request payload"}), 400

    # Validate order_id
    order_id = data.get("order_id")
    if not order_id or not isinstance(order_id, str) or not order_id.strip():
        return jsonify({"error": "Missing or invalid order_id"}), 400
    order_id = order_id.strip()

    # Validate amount
    amount = data.get("amount")
    if amount is None or isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
        return jsonify({"error": "Amount must be a positive number"}), 400

    # Validate / normalize currency
    currency = data.get("currency", "USD")
    if not isinstance(currency, str) or not currency.strip():
        currency = "USD"
    else:
        currency = currency.strip().upper()

    # Deterministic simulation control
    simulate_failure = bool(data.get("simulate_failure", False))
    simulate_status = str(data.get("simulate_status", "")).strip().lower()
    if simulate_status in ("failure", "failed", "fail") or "fail" in order_id.lower():
        simulate_failure = True

    payment_id = f"pay-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if simulate_failure:
        payment_record = {
            "payment_id": payment_id,
            "order_id": order_id,
            "amount": round(float(amount), 2),
            "currency": currency,
            "status": "failed",
            "error": "Payment declined: simulated failure",
            "timestamp": timestamp
        }
        PAYMENTS[payment_id] = payment_record
        return jsonify(payment_record), 402

    payment_record = {
        "payment_id": payment_id,
        "order_id": order_id,
        "amount": round(float(amount), 2),
        "currency": currency,
        "status": "success",
        "message": "Payment processed successfully",
        "timestamp": timestamp
    }
    PAYMENTS[payment_id] = payment_record
    return jsonify(payment_record), 200


@app.route("/payments/<payment_id>", methods=["GET"])
def get_payment(payment_id):
    """Retrieve status and details of a recorded payment."""
    pid = str(payment_id).strip()
    if pid not in PAYMENTS:
        return jsonify({
            "error": "Payment not found",
            "payment_id": payment_id
        }), 404

    return jsonify(PAYMENTS[pid]), 200


@app.route("/payments", methods=["GET"])
def list_payments():
    """List all recorded payment transactions."""
    return jsonify(list(PAYMENTS.values())), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5004))
    app.run(host="0.0.0.0", port=port)

