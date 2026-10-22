import os
# pyrefly: ignore [missing-import]
from flask import Flask, jsonify, request

app = Flask(__name__)

from fault_interceptor import init_fault_interceptor
init_fault_interceptor(app)

# In-memory realistic product catalog for the initial development stage
PRODUCTS = [
    {
        "id": "prod-1",
        "name": "Wireless Mechanical Keyboard",
        "description": "Compact mechanical keyboard with Bluetooth and 2.4GHz connectivity",
        "price": 89.99,
        "category": "Electronics"
    },
    {
        "id": "prod-2",
        "name": "Ergonomic Optical Mouse",
        "description": "High-precision vertical ergonomic wireless mouse",
        "price": 49.99,
        "category": "Electronics"
    },
    {
        "id": "prod-3",
        "name": "Noise-Cancelling Headphones",
        "description": "Over-ear active noise-cancelling wireless headphones",
        "price": 149.99,
        "category": "Audio"
    },
    {
        "id": "prod-4",
        "name": "USB-C Multi-Port Hub",
        "description": "7-in-1 USB-C hub with HDMI 4K, USB 3.0, and 100W PD charging",
        "price": 34.99,
        "category": "Accessories"
    },
    {
        "id": "prod-5",
        "name": "Laptop Stand Aluminum",
        "description": "Adjustable ventilated aluminum ergonomic laptop riser",
        "price": 29.99,
        "category": "Accessories"
    },
]


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "product-service",
        "description": "FaultLab Target Application - Product Service",
        "version": "0.1.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "product-service"
    }), 200


@app.route("/products", methods=["GET"])
def get_products():
    """Return the list of all available products."""
    return jsonify(PRODUCTS), 200


@app.route("/products/search", methods=["GET"])
def search_products():
    """Search and filter products by query parameter (q) or category."""
    query = request.args.get("q", "").strip().lower()
    category = request.args.get("category", "").strip().lower()

    results = PRODUCTS
    if category:
        results = [p for p in results if p.get("category", "").lower() == category]
    if query:
        results = [
            p for p in results
            if query in p.get("name", "").lower() or query in p.get("description", "").lower()
        ]

    return jsonify(results), 200


@app.route("/products/<product_id>", methods=["GET"])
def get_product_by_id(product_id):
    """Return a single product by ID or 404 if not found."""
    for product in PRODUCTS:
        if str(product["id"]).lower() == str(product_id).lower():
            return jsonify(product), 200

    return jsonify({
        "error": "Product not found",
        "product_id": product_id
    }), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)

