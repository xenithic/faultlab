import datetime
import os
import uuid
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

from fault_interceptor import init_fault_interceptor
init_fault_interceptor(app)

# Service Base URLs (configurable via environment variables for local dev / Docker)
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001").rstrip("/")
INVENTORY_SERVICE_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://localhost:5003").rstrip("/")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:5004").rstrip("/")

# Downstream HTTP request timeout in seconds
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "5.0"))

# Order status constants
STATUS_PENDING = "PENDING"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_FAILED = "FAILED"

# In-memory storage for orders
ORDERS = {}


def fetch_product(product_id: str) -> tuple[dict | None, str | None, int]:
    """
    Fetch product details from Product Service.

    Returns:
        tuple of (product_dict or None, error_message or None, http_status_code)
    """
    url = f"{PRODUCT_SERVICE_URL}/products/{product_id}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        return None, "Product Service request timed out", 503
    except requests.exceptions.ConnectionError:
        return None, "Unable to connect to Product Service", 503
    except requests.exceptions.RequestException as e:
        return None, f"Product Service communication error: {str(e)}", 503

    if resp.status_code == 404:
        return None, "Product not found", 404
    if resp.status_code != 200:
        return None, f"Product Service returned unexpected HTTP status {resp.status_code}", 502

    try:
        data = resp.json()
    except (ValueError, TypeError):
        return None, "Product Service returned malformed or non-JSON response", 502

    if not isinstance(data, dict) or "price" not in data:
        return None, "Product Service returned incomplete product information", 502

    return data, None, 200


def reserve_inventory(product_id: str, quantity: int) -> tuple[dict | None, str | None, int]:
    """
    Request inventory reservation from Inventory Service.

    Returns:
        tuple of (reservation_dict or None, error_message or None, http_status_code)
    """
    url = f"{INVENTORY_SERVICE_URL}/inventory/reserve"
    payload = {
        "product_id": product_id,
        "quantity": quantity
    }
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        return None, "Inventory Service request timed out", 503
    except requests.exceptions.ConnectionError:
        return None, "Unable to connect to Inventory Service", 503
    except requests.exceptions.RequestException as e:
        return None, f"Inventory Service communication error: {str(e)}", 503

    try:
        data = resp.json()
    except (ValueError, TypeError):
        data = None

    if resp.status_code == 200:
        if isinstance(data, dict):
            return data, None, 200
        return {"status": "reserved", "quantity": quantity}, None, 200

    if resp.status_code == 400:
        err_msg = data.get("error", "Insufficient stock") if isinstance(data, dict) else "Inventory reservation failed"
        return None, err_msg, 400

    if resp.status_code == 404:
        err_msg = data.get("error", "Product not found in inventory") if isinstance(data, dict) else "Product not found in inventory"
        return None, err_msg, 404

    return None, f"Inventory Service returned unexpected HTTP status {resp.status_code}", 502


def process_payment(order_id: str, amount: float, currency: str = "USD", simulation_params: dict = None) -> tuple[dict | None, str | None, int]:
    """
    Request payment processing from Payment Service.

    Returns:
        tuple of (payment_dict or None, error_message or None, http_status_code)
    """
    url = f"{PAYMENT_SERVICE_URL}/payments"
    payload = {
        "order_id": order_id,
        "amount": amount,
        "currency": currency
    }
    if simulation_params:
        payload.update(simulation_params)

    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        return None, "Payment Service request timed out", 503
    except requests.exceptions.ConnectionError:
        return None, "Unable to connect to Payment Service", 503
    except requests.exceptions.RequestException as e:
        return None, f"Payment Service communication error: {str(e)}", 503

    try:
        data = resp.json()
    except (ValueError, TypeError):
        data = None

    if resp.status_code == 200:
        if isinstance(data, dict):
            return data, None, 200
        return {"status": "success", "amount": amount}, None, 200

    if resp.status_code == 402:
        err_msg = data.get("error", "Payment declined") if isinstance(data, dict) else "Payment declined"
        return data if isinstance(data, dict) else None, err_msg, 402

    if resp.status_code == 400:
        err_msg = data.get("error", "Invalid payment parameters") if isinstance(data, dict) else "Payment request rejected"
        return data if isinstance(data, dict) else None, err_msg, 400

    return None, f"Payment Service returned unexpected HTTP status {resp.status_code}", 502


def compensate_inventory_reservation(product_id: str, quantity: int) -> dict:
    """
    Attempt to release or compensate an inventory reservation after payment failure.

    Known Architecture Limitation:
    The current Inventory Service API (v0.1.0) does not support a dedicated stock-release
    or unreserve endpoint (e.g., POST /inventory/release).
    Therefore, automated compensation cannot currently release the reserved items back into
    stock without out-of-scope manual stock mutation.
    This report explicitly documents that limitation for auditing and future follow-up.
    """
    return {
        "status": "unsupported",
        "detail": (
            "Inventory Service does not expose a stock release or unreserve endpoint. "
            "Reserved quantity could not be automatically released. "
            "Required follow-up: implement a release/compensation endpoint in Inventory Service."
        ),
        "product_id": product_id,
        "unreleased_quantity": quantity
    }


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "order-service",
        "description": "FaultLab Target Application - Order Service",
        "version": "0.1.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "order-service"
    }), 200


@app.route("/orders", methods=["POST"])
def create_order():
    """
    Create a new order, coordinating product validation, stock reservation,
    and simulated payment processing.

    Request JSON Contract:
    {
        "product_id": str (required, non-empty),
        "quantity": int (required, > 0),
        "currency": str (optional, default "USD"),
        "simulate_failure": bool (optional),
        "simulate_status": str (optional)
    }
    """
    if not request.is_json:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request payload"}), 400

    # 1. Validate request fields
    product_id = data.get("product_id")
    if not product_id or not isinstance(product_id, str) or not product_id.strip():
        return jsonify({"error": "Missing or invalid product_id"}), 400
    product_id = product_id.strip()

    quantity = data.get("quantity")
    if quantity is None or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "Quantity must be a positive integer"}), 400

    currency = data.get("currency", "USD")
    if not isinstance(currency, str) or not currency.strip():
        currency = "USD"
    else:
        currency = currency.strip().upper()

    # Optional simulation flags for payment testing
    simulation_params = {}
    if "simulate_failure" in data:
        simulation_params["simulate_failure"] = bool(data["simulate_failure"])
    if "simulate_status" in data:
        simulation_params["simulate_status"] = str(data["simulate_status"]).strip()

    # 2. Generate unique order ID
    order_id = f"ord-{uuid.uuid4().hex[:8]}"
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # 3. Retrieve product information from Product Service
    product, prod_err, prod_status = fetch_product(product_id)
    if prod_err:
        if prod_status == 404:
            return jsonify({
                "error": "Product not found",
                "product_id": product_id
            }), 404
        return jsonify({
            "error": "Failed to retrieve product details",
            "details": prod_err
        }), prod_status

    try:
        unit_price = float(product.get("price", 0.0))
    except (ValueError, TypeError):
        unit_price = 0.0
    total_amount = round(unit_price * quantity, 2)

    product_summary = {
        "id": product.get("id", product_id),
        "name": product.get("name", "Unknown Product"),
        "price": unit_price
    }

    # 4. Request inventory reservation from Inventory Service
    reservation_data, inv_err, inv_status = reserve_inventory(product_id, quantity)
    if inv_err:
        # 5. Inventory reservation failed: do NOT initiate payment.
        order_record = {
            "order_id": order_id,
            "product_id": product_id,
            "product": product_summary,
            "quantity": quantity,
            "total_amount": total_amount,
            "currency": currency,
            "status": STATUS_FAILED,
            "reservation": {
                "status": "failed",
                "error": inv_err
            },
            "payment": None,
            "error": f"Inventory reservation failed: {inv_err}",
            "created_at": created_at
        }
        ORDERS[order_id] = order_record
        return jsonify(order_record), inv_status if inv_status in (400, 404, 502, 503) else 400

    # Inventory reservation succeeded
    reservation_info = {
        "status": "reserved",
        "reserved_quantity": quantity,
        "product_id": product_id,
        "details": reservation_data
    }

    # 6. Request payment processing from Payment Service
    payment_data, pay_err, pay_status = process_payment(
        order_id=order_id,
        amount=total_amount,
        currency=currency,
        simulation_params=simulation_params
    )

    if pay_err or pay_status != 200:
        # 8. Payment failed: handle failure explicitly and attempt compensation
        compensation_info = compensate_inventory_reservation(product_id, quantity)

        order_record = {
            "order_id": order_id,
            "product_id": product_id,
            "product": product_summary,
            "quantity": quantity,
            "total_amount": total_amount,
            "currency": currency,
            "status": STATUS_FAILED,
            "reservation": reservation_info,
            "payment": payment_data if payment_data else {
                "status": "failed",
                "error": pay_err
            },
            "compensation": compensation_info,
            "error": f"Payment processing failed: {pay_err}",
            "created_at": created_at
        }
        ORDERS[order_id] = order_record
        return jsonify(order_record), pay_status if pay_status in (402, 502, 503) else 400

    # 7. Payment succeeded: mark order as confirmed
    order_record = {
        "order_id": order_id,
        "product_id": product_id,
        "product": product_summary,
        "quantity": quantity,
        "total_amount": total_amount,
        "currency": currency,
        "status": STATUS_CONFIRMED,
        "reservation": reservation_info,
        "payment": {
            "payment_id": payment_data.get("payment_id") if isinstance(payment_data, dict) else None,
            "status": "success",
            "amount": total_amount,
            "currency": currency
        },
        "created_at": created_at
    }
    ORDERS[order_id] = order_record
    return jsonify(order_record), 201


@app.route("/orders/<order_id>", methods=["GET"])
def get_order_by_id(order_id):
    """Retrieve an existing order by ID."""
    oid = str(order_id).strip()
    if oid not in ORDERS:
        return jsonify({
            "error": "Order not found",
            "order_id": order_id
        }), 404

    return jsonify(ORDERS[oid]), 200


@app.route("/orders", methods=["GET"])
def list_orders():
    """List all stored orders."""
    return jsonify(list(ORDERS.values())), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)
