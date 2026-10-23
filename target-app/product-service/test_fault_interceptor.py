import importlib.util
import os
import sys
import time
import pytest

_SERVICE_DIR = os.path.abspath(os.path.dirname(__file__))
_spec = importlib.util.spec_from_file_location("product_service_app", os.path.join(_SERVICE_DIR, "app.py"))
product_service_app = importlib.util.module_from_spec(_spec)
sys.modules["product_service_app"] = product_service_app
_spec.loader.exec_module(product_service_app)

app = product_service_app.app

# Import fault_interceptor from the service directory
_interceptor_spec = importlib.util.spec_from_file_location(
    "product_service_interceptor", os.path.join(_SERVICE_DIR, "fault_interceptor.py")
)
product_service_interceptor = importlib.util.module_from_spec(_interceptor_spec)
_interceptor_spec.loader.exec_module(product_service_interceptor)
FAULTLAB_CONTROL_SECRET = product_service_interceptor.FAULTLAB_CONTROL_SECRET


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    # Cleanup any lingering fault state
    c.delete("/_faultlab/fault", headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET})


def test_normal_traffic_unaffected(client):
    resp = client.get("/products")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_unauthorized_fault_injection_rejected(client):
    resp = client.post(
        "/_faultlab/fault",
        json={"fault_type": "latency", "latency_ms": 100},
        environ_base={"REMOTE_ADDR": "192.168.1.50"},
    )
    assert resp.status_code == 401


def test_unauthorized_status_query_rejected(client):
    resp = client.get(
        "/_faultlab/fault",
        environ_base={"REMOTE_ADDR": "192.168.1.50"},
    )
    assert resp.status_code == 401


def test_latency_injection_and_recovery(client):
    # Inject 150ms latency
    resp = client.post(
        "/_faultlab/fault",
        json={"fault_type": "latency", "latency_ms": 150, "duration_seconds": 5},
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["active"] is True
    assert data["fault_type"] == "latency"
    assert data["latency_ms"] == 150

    # Traffic experiences delay
    t0 = time.perf_counter()
    resp_traffic = client.get("/products")
    elapsed = time.perf_counter() - t0
    assert resp_traffic.status_code == 200
    assert elapsed >= 0.14  # At least 140ms

    # Health check is preserved and NOT delayed
    t_health = time.perf_counter()
    resp_health = client.get("/health")
    elapsed_health = time.perf_counter() - t_health
    assert resp_health.status_code == 200
    assert elapsed_health < 0.10

    # Clear fault
    resp_clear = client.delete(
        "/_faultlab/fault",
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp_clear.status_code == 200
    assert resp_clear.get_json()["active"] is False

    # Normal latency restored
    t1 = time.perf_counter()
    resp_after = client.get("/products")
    elapsed_after = time.perf_counter() - t1
    assert resp_after.status_code == 200
    assert elapsed_after < 0.10


def test_http_error_injection_and_recovery(client):
    # Inject HTTP 503 error
    resp = client.post(
        "/_faultlab/fault",
        json={
            "fault_type": "http_error",
            "error_code": 503,
            "error_rate": 1.0,
            "duration_seconds": 5,
        },
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp.status_code == 200
    assert resp.get_json()["active"] is True

    # Application route returns 503
    resp_traffic = client.get("/products")
    assert resp_traffic.status_code == 503
    data = resp_traffic.get_json()
    assert data["fault_type"] == "http_error"
    assert data["status_code"] == 503

    # Health check remains healthy
    resp_health = client.get("/health")
    assert resp_health.status_code == 200

    # Clear fault
    resp_clear = client.delete(
        "/_faultlab/fault",
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp_clear.status_code == 200

    # Restores to 200 OK
    resp_after = client.get("/products")
    assert resp_after.status_code == 200


def test_fault_auto_expiration(client):
    # Short 1-second fault
    client.post(
        "/_faultlab/fault",
        json={"fault_type": "http_error", "error_code": 500, "duration_seconds": 1},
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    # Active initially
    assert client.get("/products").status_code == 500

    # Wait for duration to pass
    time.sleep(1.1)

    # Automatically expires and normal traffic resumes
    resp = client.get("/products")
    assert resp.status_code == 200

    # Status reflects inactive
    st = client.get("/_faultlab/fault").get_json()
    assert st["active"] is False


def test_invalid_parameters_rejected(client):
    # Invalid fault_type
    resp = client.post(
        "/_faultlab/fault",
        json={"fault_type": "laser_beam", "duration_seconds": 5},
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp.status_code == 400

    # Invalid latency_ms
    resp2 = client.post(
        "/_faultlab/fault",
        json={"fault_type": "latency", "latency_ms": 99999},
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp2.status_code == 400

    # Invalid error_code
    resp3 = client.post(
        "/_faultlab/fault",
        json={"fault_type": "http_error", "error_code": 200},
        headers={"X-FaultLab-Secret": FAULTLAB_CONTROL_SECRET},
    )
    assert resp3.status_code == 400
