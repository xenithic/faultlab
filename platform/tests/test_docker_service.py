from unittest.mock import MagicMock
import pytest
from app.services.docker_service import (
    DockerService,
    DockerUnavailableError,
    TARGET_OPT_IN_LABEL,
    PLATFORM_LABEL,
)


def create_mock_container(
    name: str,
    service: str,
    project: str,
    status: str = "running",
    opt_in: bool = True,
    is_platform: bool = False,
    health: str = "healthy",
    cid: str = "1234567890abcdef"
):
    container = MagicMock()
    container.id = cid
    container.short_id = cid[:12]
    container.name = name
    container.status = status
    labels = {
        "com.docker.compose.project": project,
        "com.docker.compose.service": service,
    }
    if opt_in:
        labels[TARGET_OPT_IN_LABEL] = "true"
    if is_platform:
        labels[PLATFORM_LABEL] = "true"

    container.labels = labels
    container.attrs = {
        "Created": "2026-10-21T00:00:00Z",
        "State": {
            "Health": {"Status": health}
        }
    }
    return container


def test_docker_service_unavailable():
    mock_client = MagicMock()
    mock_client.ping.side_effect = Exception("Connection refused")
    service = DockerService(client=mock_client)
    assert service.is_available() is False


def test_discover_target_with_opt_in_and_allowed_services():
    c1 = create_mock_container("target-app-order-1", "order-service", "my-target-proj", cid="order_cid_12345")
    c2 = create_mock_container("target-app-product-1", "product-service", "my-target-proj", cid="prod_cid_67890")

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [c1, c2]

    service = DockerService(client=mock_client)
    result = service.discover_and_validate_target(
        compose_project="my-target-proj",
        allowed_services=["order-service", "product-service"]
    )

    assert result["validation_status"] == "valid"
    assert len(result["validation_errors"]) == 0
    assert "order-service" in result["discovered_services"]
    assert "product-service" in result["discovered_services"]
    assert result["discovered_services"]["order-service"]["primary_container"]["container_id"] == "order_cid_12345"


def test_discover_filters_platform_infrastructure():
    # Platform containers: postgres and platform backend
    pg_c = create_mock_container("faultlab-postgres-1", "postgres", "my-target-proj", is_platform=True)
    plat_c = create_mock_container("faultlab-platform-1", "faultlab-platform", "my-target-proj", is_platform=True)
    # Authorized target container
    target_c = create_mock_container("my-order-1", "order-service", "my-target-proj")

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [pg_c, plat_c, target_c]

    service = DockerService(client=mock_client)
    result = service.discover_and_validate_target(
        compose_project="my-target-proj",
        allowed_services=["order-service"]
    )

    assert result["validation_status"] == "valid"
    assert len(result["protected_containers"]) == 2
    assert "postgres" not in result["discovered_services"]
    assert "faultlab-platform" not in result["discovered_services"]
    assert "order-service" in result["discovered_services"]


def test_discover_rejects_containers_without_opt_in_label():
    # Container missing opt-in label
    unauthorized_c = create_mock_container("rogue-service-1", "rogue-service", "my-target-proj", opt_in=False)

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [unauthorized_c]

    service = DockerService(client=mock_client)
    result = service.discover_and_validate_target(
        compose_project="my-target-proj",
        allowed_services=["rogue-service"]
    )

    assert result["validation_status"] == "invalid"
    assert len(result["unauthorized_containers"]) == 1
    assert result["unauthorized_containers"][0]["service"] == "rogue-service"


def test_discover_rejects_disallowed_services():
    c_allowed = create_mock_container("my-order-1", "order-service", "my-target-proj")
    c_unwanted = create_mock_container("my-debug-1", "debug-service", "my-target-proj")

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [c_allowed, c_unwanted]

    service = DockerService(client=mock_client)
    result = service.discover_and_validate_target(
        compose_project="my-target-proj",
        allowed_services=["order-service"]
    )

    assert result["validation_status"] == "valid"
    assert "order-service" in result["discovered_services"]
    assert len(result["disallowed_containers"]) == 1
    assert result["disallowed_containers"][0]["service"] == "debug-service"


def test_discover_detects_stopped_containers():
    stopped_c = create_mock_container("my-order-1", "order-service", "my-target-proj", status="exited")

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [stopped_c]

    service = DockerService(client=mock_client)
    result = service.discover_and_validate_target(
        compose_project="my-target-proj",
        allowed_services=["order-service"]
    )

    assert result["validation_status"] == "invalid"
    assert any("no active running containers" in err for err in result["validation_errors"])


def test_validate_service_for_experiment_live():
    live_c = create_mock_container("my-order-1", "order-service", "my-proj", cid="live_container_id_abc123")

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [live_c]

    service = DockerService(client=mock_client)
    is_valid, err, c_info = service.validate_service_for_experiment(
        compose_project="my-proj",
        service_name="order-service",
        allowed_services=["order-service"]
    )

    assert is_valid is True
    assert err is None
    assert c_info["container_id"] == "live_container_id_abc123"
    assert c_info["status"] == "running"


def test_validate_service_rejects_protected():
    mock_client = MagicMock()
    service = DockerService(client=mock_client)

    is_valid, err, c_info = service.validate_service_for_experiment(
        compose_project="my-proj",
        service_name="postgres",
        allowed_services=["postgres"]
    )
    assert is_valid is False
    assert "protected platform infrastructure" in err
