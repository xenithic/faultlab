import os
from flask import Flask, jsonify, request

app = Flask(__name__)

from fault_interceptor import init_fault_interceptor
init_fault_interceptor(app)

# In-memory realistic inventory records keyed by product_id
INVENTORY = {
    "prod-1": {"product_id": "prod-1", "stock": 50},
    "prod-2": {"product_id": "prod-2", "stock": 30},
    "prod-3": {"product_id": "prod-3", "stock": 15},
    "prod-4": {"product_id": "prod-4", "stock": 100},
    "prod-5": {"product_id": "prod-5", "stock": 0},
}


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "inventory-service",
        "description": "FaultLab Target Application - Inventory Service",
        "version": "0.1.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "inventory-service"
    }), 200


@app.route("/inventory", methods=["GET"])
def get_all_inventory():
    """Return current stock levels for all products."""
    return jsonify(list(INVENTORY.values())), 200


@app.route("/inventory/<product_id>", methods=["GET"])
def check_stock(product_id):
    """Check current stock availability for a specific product."""
    pid = str(product_id).strip().lower()
    if pid not in INVENTORY:
        return jsonify({
            "error": "Product not found in inventory",
            "product_id": product_id
        }), 404

    return jsonify(INVENTORY[pid]), 200


@app.route("/inventory/reserve", methods=["POST"])
@app.route("/inventory/<product_id>/reserve", methods=["POST"])
def reserve_stock(product_id=None):
    """Reserve stock for a product, decrementing the available quantity."""
    if not request.is_json:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request payload"}), 400

    pid = (product_id or data.get("product_id", "")).strip().lower()
    if not pid:
        return jsonify({"error": "Missing product_id"}), 400

    if pid not in INVENTORY:
        return jsonify({
            "error": "Product not found in inventory",
            "product_id": pid
        }), 404

    quantity = data.get("quantity")
    if quantity is None or not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
        return jsonify({"error": "Quantity must be a positive integer"}), 400

    current_stock = INVENTORY[pid]["stock"]
    if current_stock < quantity:
        return jsonify({
            "error": "Insufficient stock",
            "product_id": pid,
            "available_stock": current_stock,
            "requested_quantity": quantity
        }), 400

    INVENTORY[pid]["stock"] -= quantity
    return jsonify({
        "message": "Stock reserved successfully",
        "product_id": pid,
        "reserved_quantity": quantity,
        "remaining_stock": INVENTORY[pid]["stock"]
    }), 200


@app.route("/inventory/<product_id>", methods=["PUT"])
@app.route("/inventory/update", methods=["POST"])
def update_stock(product_id=None):
    """Update stock level for a product."""
    if not request.is_json:
        return jsonify({"error": "Request body must be valid JSON"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request payload"}), 400

    pid = (product_id or data.get("product_id", "")).strip().lower()
    if not pid:
        return jsonify({"error": "Missing product_id"}), 400

    if pid not in INVENTORY:
        return jsonify({
            "error": "Product not found in inventory",
            "product_id": pid
        }), 404

    new_stock = data.get("stock") if "stock" in data else data.get("quantity")
    if new_stock is None or not isinstance(new_stock, int) or isinstance(new_stock, bool) or new_stock < 0:
        return jsonify({"error": "Stock must be a non-negative integer"}), 400

    INVENTORY[pid]["stock"] = new_stock
    return jsonify({
        "message": "Stock updated successfully",
        "product_id": pid,
        "stock": INVENTORY[pid]["stock"]
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5003))
    app.run(host="0.0.0.0", port=port)

