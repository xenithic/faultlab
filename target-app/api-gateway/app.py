import os
import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

from fault_interceptor import init_fault_interceptor
init_fault_interceptor(app)

# Service Base URLs (configurable via environment variables for local dev / Docker)
PRODUCT_SERVICE_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:5001").rstrip("/")
ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE_URL", "http://localhost:5002").rstrip("/")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://localhost:5004").rstrip("/")

# Gateway request timeout in seconds
GATEWAY_TIMEOUT = float(os.environ.get("GATEWAY_TIMEOUT", "5.0"))

# Hop-by-hop headers that should not be forwarded
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


def forward_request(target_base_url: str, target_path: str, service_name: str) -> Response:
    """
    Forward incoming client request to the specified downstream microservice.

    Preserves HTTP method, query parameters, request body, and downstream
    response status and headers while preventing hop-by-hop header leakage.
    Handles downstream connection errors, timeouts, and transport errors gracefully.
    """
    target_url = f"{target_base_url}{target_path}"

    # Filter incoming headers
    filtered_req_headers = {
        key: value for key, value in request.headers
        if key.lower() not in HOP_BY_HOP_HEADERS
    }

    # Prepare forwarding parameters
    kwargs = {
        "method": request.method,
        "url": target_url,
        "params": request.args,
        "headers": filtered_req_headers,
        "timeout": GATEWAY_TIMEOUT,
    }

    if request.is_json:
        kwargs["json"] = request.get_json(silent=True)
    else:
        raw_data = request.get_data()
        if raw_data:
            kwargs["data"] = raw_data

    try:
        downstream_resp = requests.request(**kwargs)
    except requests.exceptions.Timeout:
        return jsonify({
            "error": "Gateway timeout",
            "service": service_name,
            "details": f"Request to downstream {service_name} timed out after {GATEWAY_TIMEOUT} seconds"
        }), 504
    except requests.exceptions.ConnectionError:
        return jsonify({
            "error": "Service unavailable",
            "service": service_name,
            "details": f"Could not connect to downstream {service_name}"
        }), 503
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Bad gateway",
            "service": service_name,
            "details": f"Error communicating with downstream {service_name}: {str(e)}"
        }), 502

    # Filter downstream response headers to avoid hop-by-hop and stale length/encoding headers
    excluded_resp_headers = HOP_BY_HOP_HEADERS | {"content-encoding", "content-length"}
    response_headers = [
        (name, value) for name, value in downstream_resp.headers.items()
        if name.lower() not in excluded_resp_headers
    ]

    return Response(
        downstream_resp.content,
        status=downstream_resp.status_code,
        headers=response_headers,
        content_type=downstream_resp.headers.get("Content-Type", "application/json")
    )


# ----------------------------------------------------------------------
# Local Gateway Endpoints
# ----------------------------------------------------------------------

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "api-gateway",
        "description": "FaultLab Target Application - API Gateway",
        "version": "0.1.0"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "service": "api-gateway"
    }), 200


# ----------------------------------------------------------------------
# Product Service Routing
# ----------------------------------------------------------------------

@app.route("/products", methods=["GET"])
def get_products():
    return forward_request(PRODUCT_SERVICE_URL, "/products", "product-service")


@app.route("/products/search", methods=["GET"])
def search_products():
    return forward_request(PRODUCT_SERVICE_URL, "/products/search", "product-service")


@app.route("/products/<product_id>", methods=["GET"])
def get_product_by_id(product_id):
    return forward_request(PRODUCT_SERVICE_URL, f"/products/{product_id}", "product-service")


# ----------------------------------------------------------------------
# Order Service Routing
# ----------------------------------------------------------------------

@app.route("/orders", methods=["GET", "POST"])
def orders():
    return forward_request(ORDER_SERVICE_URL, "/orders", "order-service")


@app.route("/orders/<order_id>", methods=["GET"])
def get_order_by_id(order_id):
    return forward_request(ORDER_SERVICE_URL, f"/orders/{order_id}", "order-service")


# ----------------------------------------------------------------------
# Payment Service Routing (Read-only; creation is internal to Order Service)
# ----------------------------------------------------------------------

@app.route("/payments", methods=["GET"])
def get_payments():
    return forward_request(PAYMENT_SERVICE_URL, "/payments", "payment-service")


@app.route("/payments/<payment_id>", methods=["GET"])
def get_payment_by_id(payment_id):
    return forward_request(PAYMENT_SERVICE_URL, f"/payments/{payment_id}", "payment-service")


# ----------------------------------------------------------------------
# Error Handlers
# ----------------------------------------------------------------------

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Not found",
        "message": "The requested URL was not found on this API Gateway."
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method not allowed",
        "message": "The method is not allowed for the requested URL."
    }), 405


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
