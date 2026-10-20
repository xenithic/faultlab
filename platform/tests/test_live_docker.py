import os
import pytest
from app.services.docker_service import DockerService, get_docker_client


@pytest.mark.skipif(
    not os.environ.get("TEST_DOCKER"),
    reason="TEST_DOCKER environment variable not set; skipping live Docker integration tests."
)
def test_live_docker_daemon_ping():
    client = get_docker_client()
    assert client is not None
    assert client.ping() is True


@pytest.mark.skipif(
    not os.environ.get("TEST_DOCKER"),
    reason="TEST_DOCKER environment variable not set; skipping live Docker integration tests."
)
def test_live_docker_discovery_faultlab_project():
    service = DockerService()
    assert service.is_available() is True

    # The running compose project is 'faultlab'
    result = service.discover_and_validate_target(
        compose_project="faultlab",
        allowed_services=["product-service", "order-service", "inventory-service", "payment-service", "api-gateway"]
    )

    # postgres and faultlab-platform should be detected as protected
    protected_names = [p["service"] for p in result["protected_containers"]]
    assert "postgres" in protected_names or "faultlab-platform" in protected_names


@pytest.mark.skipif(
    not os.environ.get("TEST_DOCKER"),
    reason="TEST_DOCKER environment variable not set; skipping live Docker integration tests."
)
def test_live_docker_pause_unpause_cycle():
    """
    Live integration test: validates that pause and unpause work against
    the real running target environment and reliably recovers.
    """
    service = DockerService()
    is_valid, err, c_info = service.validate_service_for_experiment(
        compose_project="faultlab",
        service_name="inventory-service",
        allowed_services=["inventory-service"]
    )
    assert is_valid is True, f"Validation failed: {err}"
    cid = c_info["container_id"]

    container = service.get_validated_container(
        container_id=cid,
        expected_compose_project="faultlab",
        expected_service_name="inventory-service"
    )

    try:
        service.pause_container(container)
        state_paused = service.inspect_container_state(container)
        assert state_paused["status"] == "paused" or state_paused["paused"] is True
    finally:
        try:
            service.unpause_container(container)
        except Exception:
            pass
        state_recovered = service.inspect_container_state(container)
        assert state_recovered["status"] == "running"
