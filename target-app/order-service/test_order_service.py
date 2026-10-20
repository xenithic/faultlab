import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import requests

# Ensure target-app/order-service is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app, ORDERS, STATUS_CONFIRMED, STATUS_FAILED


class OrderServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        ORDERS.clear()

    def tearDown(self):
        ORDERS.clear()

    # 1. Base endpoints
    def test_index_and_health_endpoints(self):
        res_index = self.client.get("/")
        self.assertEqual(res_index.status_code, 200)
        data_index = res_index.get_json()
        self.assertEqual(data_index.get("service"), "order-service")
        self.assertEqual(data_index.get("version"), "0.1.0")

        res_health = self.client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        data_health = res_health.get_json()
        self.assertEqual(data_health.get("status"), "healthy")
        self.assertEqual(data_health.get("service"), "order-service")

    # 2. Successful order creation and downstream verification
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_successful_order_creation(self, mock_get, mock_post):
        # Product mock
        mock_prod_resp = MagicMock()
        mock_prod_resp.status_code = 200
        mock_prod_resp.json.return_value = {
            "id": "prod-1",
            "name": "Wireless Mechanical Keyboard",
            "price": 89.99,
            "category": "Electronics"
        }
        mock_get.return_value = mock_prod_resp

        # Inventory mock
        mock_inv_resp = MagicMock()
        mock_inv_resp.status_code = 200
        mock_inv_resp.json.return_value = {
            "message": "Stock reserved successfully",
            "product_id": "prod-1",
            "reserved_quantity": 2,
            "remaining_stock": 48
        }

        # Payment mock
        mock_pay_resp = MagicMock()
        mock_pay_resp.status_code = 200
        mock_pay_resp.json.return_value = {
            "payment_id": "pay-10001",
            "order_id": "will-be-checked",
            "amount": 179.98,
            "currency": "USD",
            "status": "success",
            "message": "Payment processed successfully"
        }

        mock_post.side_effect = [mock_inv_resp, mock_pay_resp]

        payload = {"product_id": "prod-1", "quantity": 2}
        response = self.client.post("/orders", json=payload)

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("order_id", data)
        order_id = data["order_id"]
        self.assertTrue(order_id.startswith("ord-"))
        self.assertEqual(data["status"], STATUS_CONFIRMED)
        self.assertEqual(data["product_id"], "prod-1")
        self.assertEqual(data["quantity"], 2)
        self.assertEqual(data["total_amount"], 179.98)
        self.assertEqual(data["reservation"]["status"], "reserved")
        self.assertEqual(data["payment"]["status"], "success")
        self.assertEqual(data["payment"]["payment_id"], "pay-10001")

        # Verify product get request
        mock_get.assert_called_once()
        self.assertTrue(mock_get.call_args[0][0].endswith("/products/prod-1"))

        # Verify downstream post calls (inventory then payment)
        self.assertEqual(mock_post.call_count, 2)
        inv_call = mock_post.call_args_list[0]
        self.assertTrue(inv_call[0][0].endswith("/inventory/reserve"))
        self.assertEqual(inv_call[1]["json"], {"product_id": "prod-1", "quantity": 2})

        pay_call = mock_post.call_args_list[1]
        self.assertTrue(pay_call[0][0].endswith("/payments"))
        self.assertEqual(pay_call[1]["json"]["order_id"], order_id)
        self.assertEqual(pay_call[1]["json"]["amount"], 179.98)
        self.assertEqual(pay_call[1]["json"]["currency"], "USD")

        # Verify order is stored in ORDERS
        self.assertIn(order_id, ORDERS)
        self.assertEqual(ORDERS[order_id]["status"], STATUS_CONFIRMED)

    # 3. Invalid or missing order request fields
    @patch("app.requests.get")
    @patch("app.requests.post")
    def test_invalid_or_missing_order_fields(self, mock_post, mock_get):
        # Non-JSON content type
        res = self.client.post("/orders", data="not json", content_type="text/plain")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

        # Empty body
        res = self.client.post("/orders", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Missing or invalid product_id", res.get_json()["error"])

        # Blank product_id
        res = self.client.post("/orders", json={"product_id": "   ", "quantity": 1})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Missing or invalid product_id", res.get_json()["error"])

        # Non-string product_id
        res = self.client.post("/orders", json={"product_id": 12345, "quantity": 1})
        self.assertEqual(res.status_code, 400)

        # Missing quantity
        res = self.client.post("/orders", json={"product_id": "prod-1"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Quantity must be a positive integer", res.get_json()["error"])

        # Zero quantity
        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 0})
        self.assertEqual(res.status_code, 400)

        # Negative quantity
        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": -5})
        self.assertEqual(res.status_code, 400)

        # Boolean quantity (True)
        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": True})
        self.assertEqual(res.status_code, 400)

        # Float quantity
        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 2.5})
        self.assertEqual(res.status_code, 400)

        # Verify no downstream calls occurred
        mock_get.assert_not_called()
        mock_post.assert_not_called()
        self.assertEqual(len(ORDERS), 0)

    # 4. Product not found
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_product_not_found(self, mock_get, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "Product not found", "product_id": "prod-unknown"}
        mock_get.return_value = mock_resp

        response = self.client.post("/orders", json={"product_id": "prod-unknown", "quantity": 1})
        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertEqual(data["error"], "Product not found")
        self.assertEqual(data["product_id"], "prod-unknown")

        # Downstream post must not be called
        mock_post.assert_not_called()
        self.assertEqual(len(ORDERS), 0)

    # 5. Product service unavailable / timeout
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_product_service_unavailable(self, mock_get, mock_post):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        response = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertIn("Failed to retrieve product details", data["error"])

        mock_post.assert_not_called()
        self.assertEqual(len(ORDERS), 0)

    # 6. Inventory reservation failure: payment must not be called
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_inventory_reservation_failure_insufficient_stock(self, mock_get, mock_post):
        # Product mock
        mock_prod_resp = MagicMock()
        mock_prod_resp.status_code = 200
        mock_prod_resp.json.return_value = {"id": "prod-1", "name": "Keyboard", "price": 89.99}
        mock_get.return_value = mock_prod_resp

        # Inventory mock (400 Insufficient stock)
        mock_inv_resp = MagicMock()
        mock_inv_resp.status_code = 400
        mock_inv_resp.json.return_value = {
            "error": "Insufficient stock",
            "product_id": "prod-1",
            "available_stock": 1,
            "requested_quantity": 10
        }
        mock_post.return_value = mock_inv_resp

        response = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 10})
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["status"], STATUS_FAILED)
        self.assertEqual(data["reservation"]["status"], "failed")
        self.assertIsNone(data["payment"])
        self.assertIn("Insufficient stock", data["error"])

        # Inventory called once, payment NEVER called
        self.assertEqual(mock_post.call_count, 1)
        self.assertTrue(mock_post.call_args[0][0].endswith("/inventory/reserve"))

        # Order is recorded as FAILED
        order_id = data["order_id"]
        self.assertIn(order_id, ORDERS)
        self.assertEqual(ORDERS[order_id]["status"], STATUS_FAILED)

    # 7. Inventory service unavailable / timed out
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_inventory_service_unavailable(self, mock_get, mock_post):
        mock_prod_resp = MagicMock()
        mock_prod_resp.status_code = 200
        mock_prod_resp.json.return_value = {"id": "prod-1", "name": "Keyboard", "price": 89.99}
        mock_get.return_value = mock_prod_resp

        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")

        response = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data["status"], STATUS_FAILED)
        self.assertEqual(data["reservation"]["status"], "failed")
        self.assertIsNone(data["payment"])

        # Payment was not called
        self.assertEqual(mock_post.call_count, 1)

    # 8. Payment failure after successful reservation
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_payment_failure_after_reservation(self, mock_get, mock_post):
        mock_prod_resp = MagicMock()
        mock_prod_resp.status_code = 200
        mock_prod_resp.json.return_value = {"id": "prod-1", "name": "Keyboard", "price": 89.99}
        mock_get.return_value = mock_prod_resp

        # Inventory succeeds
        mock_inv_resp = MagicMock()
        mock_inv_resp.status_code = 200
        mock_inv_resp.json.return_value = {"message": "Stock reserved successfully"}

        # Payment fails with 402 Payment Required
        mock_pay_resp = MagicMock()
        mock_pay_resp.status_code = 402
        mock_pay_resp.json.return_value = {
            "payment_id": "pay-fail01",
            "status": "failed",
            "error": "Payment declined: simulated failure"
        }

        mock_post.side_effect = [mock_inv_resp, mock_pay_resp]

        response = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(response.status_code, 402)
        data = response.get_json()
        self.assertEqual(data["status"], STATUS_FAILED)
        self.assertEqual(data["reservation"]["status"], "reserved")
        self.assertEqual(data["payment"]["status"], "failed")
        self.assertIn("compensation", data)
        self.assertEqual(data["compensation"]["status"], "unsupported")
        self.assertIn("does not expose a stock release", data["compensation"]["detail"])

        # Order is recorded as FAILED
        order_id = data["order_id"]
        self.assertIn(order_id, ORDERS)
        self.assertEqual(ORDERS[order_id]["status"], STATUS_FAILED)

    # 9. Payment service unavailable / timed out
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_payment_service_timeout(self, mock_get, mock_post):
        mock_prod_resp = MagicMock()
        mock_prod_resp.status_code = 200
        mock_prod_resp.json.return_value = {"id": "prod-1", "name": "Keyboard", "price": 89.99}
        mock_get.return_value = mock_prod_resp

        # Inventory succeeds
        mock_inv_resp = MagicMock()
        mock_inv_resp.status_code = 200
        mock_inv_resp.json.return_value = {"message": "Stock reserved successfully"}

        # Payment times out
        mock_post.side_effect = [mock_inv_resp, requests.exceptions.Timeout("Read timeout")]

        response = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data["status"], STATUS_FAILED)
        self.assertEqual(data["payment"]["status"], "failed")
        self.assertIn("timed out", data["payment"]["error"])
        self.assertEqual(data["compensation"]["status"], "unsupported")

    # 10. Retrieval of existing and unknown orders
    def test_get_order_existing_and_unknown(self):
        # Insert test order directly into ORDERS
        test_order = {
            "order_id": "ord-test1234",
            "product_id": "prod-1",
            "quantity": 3,
            "status": STATUS_CONFIRMED,
            "total_amount": 269.97
        }
        ORDERS["ord-test1234"] = test_order

        # Existing order retrieval
        res_existing = self.client.get("/orders/ord-test1234")
        self.assertEqual(res_existing.status_code, 200)
        self.assertEqual(res_existing.get_json()["order_id"], "ord-test1234")
        self.assertEqual(res_existing.get_json()["status"], STATUS_CONFIRMED)

        # Unknown order retrieval
        res_unknown = self.client.get("/orders/ord-nonexistent")
        self.assertEqual(res_unknown.status_code, 404)
        self.assertEqual(res_unknown.get_json()["error"], "Order not found")

        # List orders
        res_list = self.client.get("/orders")
        self.assertEqual(res_list.status_code, 200)
        orders_list = res_list.get_json()
        self.assertEqual(len(orders_list), 1)
        self.assertEqual(orders_list[0]["order_id"], "ord-test1234")

    # 11. Handling downstream unexpected responses (malformed JSON, 500 status codes)
    @patch("app.requests.post")
    @patch("app.requests.get")
    def test_unexpected_downstream_responses(self, mock_get, mock_post):
        # Case A: Product service returns 500 Internal Server Error
        mock_prod_500 = MagicMock()
        mock_prod_500.status_code = 500
        mock_get.return_value = mock_prod_500

        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(res.status_code, 502)
        self.assertIn("unexpected HTTP status 500", res.get_json()["details"])

        # Case B: Product service returns non-JSON / HTML
        mock_prod_html = MagicMock()
        mock_prod_html.status_code = 200
        mock_prod_html.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_prod_html

        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(res.status_code, 502)
        self.assertIn("malformed or non-JSON", res.get_json()["details"])

        # Case C: Inventory service returns 500 status code
        mock_prod_ok = MagicMock()
        mock_prod_ok.status_code = 200
        mock_prod_ok.json.return_value = {"id": "prod-1", "name": "Keyboard", "price": 89.99}
        mock_get.return_value = mock_prod_ok

        mock_inv_500 = MagicMock()
        mock_inv_500.status_code = 500
        mock_post.return_value = mock_inv_500

        res = self.client.post("/orders", json={"product_id": "prod-1", "quantity": 1})
        self.assertEqual(res.status_code, 502)
        data = res.get_json()
        self.assertEqual(data["status"], STATUS_FAILED)
        self.assertIn("unexpected HTTP status 500", data["error"])


if __name__ == "__main__":
    unittest.main()
