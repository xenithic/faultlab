import pytest
from app import create_app, db


@pytest.fixture
def client():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as test_client:
            yield test_client
        db.drop_all()


def test_index_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["service"] == "faultlab-platform"
    assert "description" in data
    assert data["version"] == "0.1.0"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "faultlab-platform"
    assert data["version"] == "0.1.0"


def test_health_db_endpoint(client):
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_not_found_json_response(client):
    response = client.get("/api/unknown-route")
    assert response.status_code == 404
    data = response.get_json()
    assert data["error"] == "Not Found"
    assert "message" in data


def test_method_not_allowed_json_response(client):
    response = client.post("/health")
    assert response.status_code == 405
    data = response.get_json()
    assert data["error"] == "Method Not Allowed"
    assert "message" in data
