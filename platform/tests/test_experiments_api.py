from unittest.mock import patch
import pytest
from app import create_app, db
from app.models import RegisteredTarget, Experiment
from app.services import DockerUnavailableError


@pytest.fixture
def client():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        with app.test_client() as test_client:
            yield test_client
        db.session.rollback()
        db.drop_all()


def create_validated_target():
    target = RegisteredTarget(
        name="valid-target",
        compose_project="proj-1",
        allowed_services=["order-service", "product-service"],
        validation_status="valid",
        status="active"
    )
    db.session.add(target)
    db.session.commit()
    return target


@patch("app.routes.experiments.DockerService.validate_service_for_experiment")
def test_create_experiment_success(mock_validate, client):
    mock_validate.return_value = (
        True,
        None,
        {"container_id": "cid_valid_987654321", "service": "order-service", "status": "running"}
    )

    target = create_validated_target()

    payload = {
        "target_id": target.id,
        "fault_type": "service_failure",
        "target_service": "order-service",
        "parameters": {"duration_seconds": 20}
    }

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["status"] == "pending"
    assert data["target_service"] == "order-service"
    assert data["target_container_id"] == "cid_valid_987654321"
    assert data["fault_type"] == "service_failure"


def test_create_experiment_unvalidated_target_rejected(client):
    target = RegisteredTarget(
        name="unvalidated-target",
        compose_project="proj-1",
        allowed_services=["order-service"],
        validation_status="unvalidated",
        status="active"
    )
    db.session.add(target)
    db.session.commit()

    payload = {
        "target_id": target.id,
        "fault_type": "service_failure",
        "target_service": "order-service"
    }

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 400
    assert "must have validation_status 'valid'" in resp.get_json()["message"]


def test_create_experiment_disallowed_service_rejected(client):
    target = create_validated_target()

    payload = {
        "target_id": target.id,
        "fault_type": "service_failure",
        "target_service": "unlisted-service"
    }

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 400
    assert "allowed_services" in resp.get_json()["message"]


def test_create_experiment_invalid_fault_type_rejected(client):
    target = create_validated_target()

    payload = {
        "target_id": target.id,
        "fault_type": "arbitrary_destruction",
        "target_service": "order-service"
    }

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 400
    assert "fault_type" in resp.get_json()["message"]


@patch("app.routes.experiments.DockerService.validate_service_for_experiment")
def test_create_experiment_fresh_validation_fails_stopped_container(mock_validate, client):
    # Live docker check reports container is stopped
    mock_validate.return_value = (
        False,
        "Service 'order-service' has no running container instances (order-service-1: exited).",
        None
    )

    target = create_validated_target()

    payload = {
        "target_id": target.id,
        "fault_type": "service_failure",
        "target_service": "order-service"
    }

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 400
    assert "no running container instances" in resp.get_json()["message"]


@patch("app.routes.experiments.DockerService.validate_service_for_experiment")
def test_create_experiment_docker_unavailable(mock_validate, client):
    mock_validate.side_effect = DockerUnavailableError("Docker daemon connection failed")

    target = create_validated_target()

    payload = {
        "target_id": target.id,
        "fault_type": "service_failure",
        "target_service": "order-service"
    }

    resp = client.post("/api/experiments", json=payload)
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "Docker Unavailable"


@patch("app.routes.experiments.DockerService.validate_service_for_experiment")
def test_experiment_lifecycle_and_cancellation(mock_validate, client):
    mock_validate.return_value = (
        True,
        None,
        {"container_id": "cid_abc123", "service": "order-service", "status": "running"}
    )

    target = create_validated_target()

    # 1. Create experiment
    res_create = client.post("/api/experiments", json={
        "target_id": target.id,
        "fault_type": "latency",
        "target_service": "order-service",
        "parameters": {"delay_ms": 500}
    })
    assert res_create.status_code == 201
    exp_id = res_create.get_json()["id"]

    # 2. Get experiment
    res_get = client.get(f"/api/experiments/{exp_id}")
    assert res_get.status_code == 200
    assert res_get.get_json()["status"] == "pending"

    # 3. List experiments with filtering
    res_list = client.get(f"/api/experiments?target_id={target.id}&status=pending")
    assert res_list.status_code == 200
    assert len(res_list.get_json()) == 1

    # 4. Cancel pending experiment
    res_cancel = client.post(f"/api/experiments/{exp_id}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.get_json()["experiment"]["status"] == "cancelled"

    # 5. Cancelling already cancelled experiment should fail
    res_re_cancel = client.post(f"/api/experiments/{exp_id}/cancel")
    assert res_re_cancel.status_code == 400
    assert "Only 'pending' experiments can be cancelled" in res_re_cancel.get_json()["message"]
