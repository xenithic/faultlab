import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import requests

# Ensure target-app/api-gateway is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app


class ApiGatewayTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    # 1. Local Gateway endpoints
    def test_local_index_and_health(self):
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        data_index = res_index.get_json()
        self.assertEqual(data_index.get("service"), "api-gateway")
        self.assertEqual(data_index.get("version"), "0.1.0")

        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        data_health = res_health.get_json()
        self.assertEqual(data_health.get("status"), "healthy")
        self.assertEqual(data_health.get("service"), "api-gateway")

    # 2. Product listing forwarding
    @patch("app.requests.request")
    def test_products_listing(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps([{"id": "prod-1", "name": "Keyboard"}]).encode("utf-8")
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp

        res = self.client.get("/products")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [{"id": "prod-1", "name": "Keyboard"}])

        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/products"))

    # 3. Product search with query parameter forwarding
    @patch("app.requests.request")
    def test_products_search_with_params(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps([{"id": "prod-1"}]).encode("utf-8")
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp

        res = self.client.get("/products/search?q=wireless&category=Electronics")
        self.assertEqual(res.status_code, 200)

        mock_request.assert_called_once()
        kwargs = mock_request.call_args[1]
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/products/search"))
        self.assertEqual(kwargs["params"].get("q"), "wireless")
        self.assertEqual(kwargs["params"].get("category"), "Electronics")

    # 4. Product details by ID forwarding
    @patch("app.requests.request")
    def test_product_by_id(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps({"id": "prod-1", "price": 89.99}).encode("utf-8")
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp

        res = self.client.get("/products/prod-1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["id"], "prod-1")

        mock_request.assert_called_once()
        kwargs = mock_request.call_args[1]
        self.assertEqual(kwargs["method"], "GET")
        self.assertTrue(kwargs["url"].endswith("/products/prod-1"))

    # 5. Order creation forwarding with JSON body
    @patch("app.requests.request")
    def test_order_creation_forwarding(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        order_data = {
            "order_id": "ord-12345",
            "product_id": "prod-1",
            "quantity": 2,
            "status": "CONFIRMED"
        }
        mock_resp.content = json.dumps(order_data).encode("utf-8")
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp

        payload = {"product_id": "prod-1", "quantity": 2}
        res = self.client.post("/orders", json=payload)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.get_json()["status"], "CONFIRMED")
        self.assertEqual(res.get_json()["order_id"], "ord-12345")

        mock_request.assert_called_once()
        kwargs = mock_request.call_args[1]
        self.assertEqual(kwargs["method"], "POST")
        self.assertTrue(kwargs["url"].endswith("/orders"))
        self.assertEqual(kwargs["json"], payload)

    # 6. Order listing and retrieval forwarding
    @patch("app.requests.request")
    def test_order_listing_and_retrieval(self, mock_request):
        # Listing
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps([{"order_id": "ord-1"}]).encode("utf-8")
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp

        res_list = self.client.get("/orders")
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.get_json()), 1)

        # Retrieval by ID
        mock_resp_detail = MagicMock()
        mock_resp_detail.status_code = 200
        mock_resp_detail.content = json.dumps({"order_id": "ord-1", "status": "CONFIRMED"}).encode("utf-8")
        mock_resp_detail.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp_detail

        res_detail = self.client.get("/orders/ord-1")
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.get_json()["order_id"], "ord-1")

    # 7. Payment listing and detail forwarding (GET only)
    @patch("app.requests.request")
    def test_payment_listing_and_detail(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = json.dumps([{"payment_id": "pay-1"}]).encode("utf-8")
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp

        res_list = self.client.get("/payments")
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(res_list.get_json()[0]["payment_id"], "pay-1")

        mock_resp_detail = MagicMock()
        mock_resp_detail.status_code = 200
        mock_resp_detail.content = json.dumps({"payment_id": "pay-1", "amount": 89.99}).encode("utf-8")
        mock_resp_detail.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_resp_detail

        res_detail = self.client.get("/payments/pay-1")
        self.assertEqual(res_detail.status_code, 200)
        self.assertEqual(res_detail.get_json()["amount"], 89.99)

    # 8. POST /payments is NOT exposed on gateway
    def test_post_payments_not_allowed(self):
        res = self.client.post("/payments", json={"amount": 100})
        self.assertEqual(res.status_code, 405)
        self.assertEqual(res.get_json()["error"], "Method not allowed")

    # 9. Direct /inventory routes are NOT exposed on gateway
    def test_inventory_routes_not_exposed(self):
        res = self.client.get("/inventory")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.get_json()["error"], "Not found")

        res_reserve = self.client.post("/inventory/reserve", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(res_reserve.status_code, 404)

    # 10. Status code preservation (400, 402, 404)
    @patch("app.requests.request")
    def test_status_code_preservation(self, mock_request):
        # Case 1: 400 Bad Request
        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.content = json.dumps({"error": "Quantity must be positive"}).encode("utf-8")
        mock_400.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_400

        res_400 = self.client.post("/orders", json={"product_id": "prod-1", "quantity": -1})
        self.assertEqual(res_400.status_code, 400)
        self.assertEqual(res_400.get_json()["error"], "Quantity must be positive")

        # Case 2: 402 Payment Required
        mock_402 = MagicMock()
        mock_402.status_code = 402
        mock_402.content = json.dumps({"error": "Payment declined", "status": "FAILED"}).encode("utf-8")
        mock_402.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_402

        res_402 = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(res_402.status_code, 402)
        self.assertEqual(res_402.get_json()["error"], "Payment declined")

        # Case 3: 404 Product Not Found
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_404.content = json.dumps({"error": "Product not found"}).encode("utf-8")
        mock_404.headers = {"Content-Type": "application/json"}
        mock_request.return_value = mock_404

        res_404 = self.client.get("/products/unknown-prod")
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.get_json()["error"], "Product not found")

    # 11. Downstream connection failure returns 503
    @patch("app.requests.request")
    def test_downstream_connection_error(self, mock_request):
        mock_request.side_effect = requests.exceptions.ConnectionError("Connection refused")

        res = self.client.get("/products")
        self.assertEqual(res.status_code, 503)
        data = res.get_json()
        self.assertEqual(data["error"], "Service unavailable")
        self.assertEqual(data["service"], "product-service")
        self.assertIn("Could not connect", data["details"])

    # 12. Downstream timeout returns 504
    @patch("app.requests.request")
    def test_downstream_timeout(self, mock_request):
        mock_request.side_effect = requests.exceptions.Timeout("Read timed out")

        res = self.client.get("/orders")
        self.assertEqual(res.status_code, 504)
        data = res.get_json()
        self.assertEqual(data["error"], "Gateway timeout")
        self.assertEqual(data["service"], "order-service")
        self.assertIn("timed out", data["details"])

    # 13. Unknown Gateway route returns 404
    def test_unknown_gateway_route(self):
        res = self.client.get("/nonexistent/api/path")
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertEqual(data["error"], "Not found")

    # 14. Hop-by-hop headers filtering and clean response headers
    @patch("app.requests.request")
    def test_header_filtering(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "ok"}'
        mock_resp.headers = {
            "Content-Type": "application/json",
            "Transfer-Encoding": "chunked",
            "Connection": "keep-alive",
            "Content-Length": "999",  # deliberately stale / mismatched
            "X-Custom-Header": "FaultLab"
        }
        mock_request.return_value = mock_resp

        res = self.client.get("/products")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("Transfer-Encoding", res.headers)
        self.assertNotIn("Connection", res.headers)
        # Content-Length should match the actual response body length (16 bytes), not 999
        self.assertEqual(res.headers.get("Content-Length"), str(len(b'{"status": "ok"}')))
        self.assertEqual(res.headers.get("X-Custom-Header"), "FaultLab")


if __name__ == "__main__":
    unittest.main()
