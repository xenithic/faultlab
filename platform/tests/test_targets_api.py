from unittest.mock import patch
import pytest
from app import create_app, db
from app.models import RegisteredTarget


@pytest.fixture
def client():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as test_client:
            yield test_client
        db.session.rollback()
        db.drop_all()


def test_register_target_valid(client):
    payload = {
        "name": "ecommerce-target",
        "compose_project": "faultlab",
        "description": "Controlled target microservices",
        "allowed_services": ["order-service", "product-service"]
    }
    resp = client.post("/api/targets", json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "ecommerce-target"
    assert data["compose_project"] == "faultlab"
    assert data["allowed_services"] == ["order-service", "product-service"]
    assert data["validation_status"] == "unvalidated"


def test_register_target_duplicate_name(client):
    payload = {
        "name": "dup-target",
        "compose_project": "proj-1",
        "allowed_services": ["order-service"]
    }
    resp1 = client.post("/api/targets", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/api/targets", json=payload)
    assert resp2.status_code == 409
    assert resp2.get_json()["error"] == "Conflict"


def test_register_target_missing_allowed_services(client):
    # Empty allowed_services must be rejected
    payload = {
        "name": "empty-allowed",
        "compose_project": "proj-1",
        "allowed_services": []
    }
    resp = client.post("/api/targets", json=payload)
    assert resp.status_code == 400
    assert "allowed_services" in resp.get_json()["message"]


def test_register_target_rejects_protected_services(client):
    payload = {
        "name": "target-with-postgres",
        "compose_project": "proj-1",
        "allowed_services": ["order-service", "postgres"]
    }
    resp = client.post("/api/targets", json=payload)
    assert resp.status_code == 400
    assert "Protected platform components" in resp.get_json()["message"]


def test_list_targets(client):
    client.post("/api/targets", json={"name": "t1", "compose_project": "p1", "allowed_services": ["s1"]})
    client.post("/api/targets", json={"name": "t2", "compose_project": "p2", "allowed_services": ["s2"]})

    resp = client.get("/api/targets")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


def test_get_target_by_id(client):
    res_create = client.post("/api/targets", json={"name": "t1", "compose_project": "p1", "allowed_services": ["s1"]})
    target_id = res_create.get_json()["id"]

    res_get = client.get(f"/api/targets/{target_id}")
    assert res_get.status_code == 200
    assert res_get.get_json()["name"] == "t1"

    res_unknown = client.get("/api/targets/99999")
    assert res_unknown.status_code == 404


@patch("app.routes.targets.DockerService.discover_and_validate_target")
def test_validate_target_endpoint(mock_discover, client):
    mock_discover.return_value = {
        "validation_status": "valid",
        "validation_errors": [],
        "discovered_services": {
            "order-service": {
                "service": "order-service",
                "running_instances_count": 1
            }
        },
        "unauthorized_containers": [],
        "disallowed_containers": [],
        "protected_containers": []
    }

    res_create = client.post("/api/targets", json={"name": "t1", "compose_project": "p1", "allowed_services": ["order-service"]})
    target_id = res_create.get_json()["id"]

    res_validate = client.post(f"/api/targets/{target_id}/validate")
    assert res_validate.status_code == 200
    data = res_validate.get_json()
    assert data["target"]["validation_status"] == "valid"
    assert "order-service" in data["target"]["discovered_services"]


def test_delete_target_cascades_experiments(client):
    # 1. Create target
    res_create = client.post("/api/targets", json={"name": "to-delete", "compose_project": "p1", "allowed_services": ["s1"]})
    target_id = res_create.get_json()["id"]

    # 2. Add an experiment record associated with this target
    from app import db
    from app.models import Experiment
    exp = Experiment(
        target_id=target_id,
        fault_type="service_failure",
        target_service="s1",
        target_container_id="c_test_del_123",
        status="pending"
    )
    db.session.add(exp)
    db.session.commit()
    exp_id = exp.id

    assert Experiment.query.filter_by(target_id=target_id).count() == 1

    # 3. Delete target via API
    res_del = client.delete(f"/api/targets/{target_id}")
    assert res_del.status_code == 200

    # 4. Verify both target and its experiments are deleted
    assert client.get(f"/api/targets/{target_id}").status_code == 404
    assert client.get(f"/api/experiments/{exp_id}").status_code == 404
    assert Experiment.query.filter_by(target_id=target_id).count() == 0
