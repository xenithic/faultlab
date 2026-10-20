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
