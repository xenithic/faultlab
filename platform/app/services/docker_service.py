import logging
from typing import Any
import docker
from docker.errors import DockerException

logger = logging.getLogger(__name__)

# Mandatory generic opt-in label required on any container to be eligible as a FaultLab target
TARGET_OPT_IN_LABEL = "faultlab.target"
TARGET_OPT_IN_VALUE = "true"

# Explicit label identifying platform infrastructure components
PLATFORM_LABEL = "faultlab.platform"

# Names and services explicitly protected from resilience testing
PROTECTED_SERVICES = {"postgres", "faultlab-platform"}


class DockerUnavailableError(Exception):
    """Raised when the Docker daemon is unreachable or disconnected."""
    pass


class ContainerSecurityError(Exception):
    """Raised when an operation targets an unauthorized or protected container."""
    pass


class ContainerNotFoundError(Exception):
    """Raised when a specified container is not found on the host."""
    pass


class ContainerStateError(Exception):
    """Raised when a container is in an incompatible state for the requested operation."""
    pass


def get_docker_client() -> docker.DockerClient | None:
    """
    Safely obtain a Docker client instance.
    Supports local Windows named pipe (Docker Desktop) and Linux container socket.
    Returns None if the daemon cannot be reached.
    """
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        logger.warning("Docker daemon is unreachable: %s", str(e))
        return None


class DockerService:
    """
    Encapsulates all Docker SDK inspection and discovery operations.
    Strictly read-only in Milestone 2: does not stop, restart, pause, or modify containers.
    """

    def __init__(self, client: docker.DockerClient | None = None):
        self._client = client

    @property
    def client(self) -> docker.DockerClient:
        if self._client is not None:
            return self._client
        client = get_docker_client()
        if client is None:
            raise DockerUnavailableError("Docker daemon is unavailable or unreachable.")
        return client

    def is_available(self) -> bool:
        """Check whether the Docker daemon responds to ping."""
        try:
            client = self.client
            client.ping()
            return True
        except Exception:
            return False

    def discover_and_validate_target(
        self,
        compose_project: str,
        allowed_services: list[str]
    ) -> dict[str, Any]:
        """
        Discover and inspect containers belonging to a Compose project.
        Enforces target authorization:
        1. Container must match com.docker.compose.project == compose_project.
        2. Container must possess generic opt-in label 'faultlab.target=true'.
        3. Container must NOT be protected platform infrastructure.
        4. Container service must be explicitly listed in allowed_services.

        Returns discovery breakdown and overall validation result.
        """
        client = self.client

        # Ensure allowed_services is an explicit non-empty list
        allowed_set = set(allowed_services or [])
        if not allowed_set:
            return {
                "validation_status": "invalid",
                "reason": "An explicit, non-empty allowed_services list is required to validate a target.",
                "discovered_services": {},
                "unauthorized_containers": [],
                "disallowed_containers": [],
                "protected_containers": [],
            }

        try:
            # Query all containers matching the compose project
            containers = client.containers.list(
                all=True,
                filters={"label": f"com.docker.compose.project={compose_project}"}
            )
        except DockerException as e:
            raise DockerUnavailableError(f"Docker API error querying containers: {str(e)}") from e

        discovered_services: dict[str, dict[str, Any]] = {}
        unauthorized_containers: list[dict[str, str]] = []
        disallowed_containers: list[dict[str, str]] = []
        protected_containers: list[dict[str, str]] = []
        validation_errors: list[str] = []

        for container in containers:
            labels = container.labels or {}
            c_name = container.name
            c_service = labels.get("com.docker.compose.service", "")

            # 1. Filter out platform infrastructure
            is_platform_labeled = str(labels.get(PLATFORM_LABEL, "")).lower() == "true"
            is_protected_name = c_service.lower() in PROTECTED_SERVICES or any(
                p in c_name.lower() for p in PROTECTED_SERVICES
            )

            if is_platform_labeled or is_protected_name:
                protected_containers.append({
                    "id": container.short_id,
                    "name": c_name,
                    "service": c_service,
                    "reason": "Platform infrastructure protected"
                })
                continue

            # 2. Check generic opt-in label
            opt_in = str(labels.get(TARGET_OPT_IN_LABEL, "")).lower() == TARGET_OPT_IN_VALUE
            if not opt_in:
                unauthorized_containers.append({
                    "id": container.short_id,
                    "name": c_name,
                    "service": c_service,
                    "reason": f"Missing required label '{TARGET_OPT_IN_LABEL}={TARGET_OPT_IN_VALUE}'"
                })
                continue

            # 3. Check explicit allowlist
            if c_service not in allowed_set:
                disallowed_containers.append({
                    "id": container.short_id,
                    "name": c_name,
                    "service": c_service,
                    "reason": f"Service '{c_service}' is not in the target's explicit allowed_services list"
                })
                continue

            # 4. Service is authorized, opt-in, and allowed
            health_status = (
                container.attrs.get("State", {})
                .get("Health", {})
                .get("Status", "none")
            )

            c_info = {
                "container_id": container.id,
                "container_short_id": container.short_id,
                "container_name": c_name,
                "status": container.status,  # "running", "exited", "created", etc.
                "health": health_status,
                "created_at": container.attrs.get("Created"),
            }

            if c_service not in discovered_services:
                discovered_services[c_service] = {
                    "service": c_service,
                    "is_allowed": True,
                    "opt_in": True,
                    "primary_container": c_info,
                    "instances": [c_info],
                    "running_instances_count": 1 if container.status == "running" else 0,
                    "total_instances_count": 1,
                }
            else:
                discovered_services[c_service]["instances"].append(c_info)
                discovered_services[c_service]["total_instances_count"] += 1
                if container.status == "running":
                    discovered_services[c_service]["running_instances_count"] += 1
                    # If existing primary is not running, replace with running instance
                    if discovered_services[c_service]["primary_container"]["status"] != "running":
                        discovered_services[c_service]["primary_container"] = c_info

        # 5. Check missing allowed services
        missing_allowed = allowed_set - set(discovered_services.keys())
        if missing_allowed:
            validation_errors.append(
                f"The following allowed services were not found with opt-in labels: {sorted(missing_allowed)}"
            )

        # 6. Check that every discovered allowed service has an active running container
        inactive_services = [
            svc for svc, data in discovered_services.items()
            if data["running_instances_count"] == 0
        ]
        if inactive_services:
            validation_errors.append(
                f"The following services have no active running containers: {sorted(inactive_services)}"
            )

        is_valid = len(discovered_services) > 0 and len(validation_errors) == 0

        return {
            "validation_status": "valid" if is_valid else "invalid",
            "validation_errors": validation_errors,
            "discovered_services": discovered_services,
            "unauthorized_containers": unauthorized_containers,
            "disallowed_containers": disallowed_containers,
            "protected_containers": protected_containers,
        }

    def validate_service_for_experiment(
        self,
        compose_project: str,
        service_name: str,
        allowed_services: list[str]
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """
        Perform fresh, live Docker inspection to authorize and bind a pending experiment.
        Never relies on cached data.
        Returns: (is_valid, error_message, container_info_dict)
        """
        # 1. Check explicit allowlist
        if not allowed_services or service_name not in allowed_services:
            return False, f"Service '{service_name}' is not in the target's explicit allowed_services list.", None

        # 2. Check protected infrastructure blacklist
        if service_name.lower() in PROTECTED_SERVICES:
            return False, f"Service '{service_name}' is a protected platform infrastructure component and cannot be targeted.", None

        # 3. Query live Docker containers for the specific service
        try:
            client = self.client
            containers = client.containers.list(
                all=True,
                filters={
                    "label": [
                        f"com.docker.compose.project={compose_project}",
                        f"com.docker.compose.service={service_name}",
                    ]
                }
            )
        except DockerException as e:
            return False, f"Docker daemon communication error during live validation: {str(e)}", None

        if not containers:
            return False, f"Service '{service_name}' container not found in project '{compose_project}'.", None

        # 4. Check opt-in label on the container
        authorized_containers = [
            c for c in containers
            if str(c.labels.get(TARGET_OPT_IN_LABEL, "")).lower() == TARGET_OPT_IN_VALUE
            and str(c.labels.get(PLATFORM_LABEL, "")).lower() != "true"
        ]

        if not authorized_containers:
            return False, f"Service '{service_name}' is missing the required '{TARGET_OPT_IN_LABEL}={TARGET_OPT_IN_VALUE}' opt-in label.", None

        # 5. Check container running state
        running_containers = [c for c in authorized_containers if c.status == "running"]
        if not running_containers:
            status_summary = ", ".join([f"{c.name}: {c.status}" for c in authorized_containers])
            return False, f"Service '{service_name}' has no running container instances ({status_summary}).", None

        # 6. Select primary running instance and record replica metadata if multiple
        selected_container = running_containers[0]
        health_status = (
            selected_container.attrs.get("State", {})
            .get("Health", {})
            .get("Status", "none")
        )

        container_info = {
            "container_id": selected_container.id,
            "container_short_id": selected_container.short_id,
            "container_name": selected_container.name,
            "service": service_name,
            "status": selected_container.status,
            "health": health_status,
            "replica_count": len(running_containers),
            "multiple_replicas_detected": len(running_containers) > 1,
        }

        return True, None, container_info

    def get_validated_container(
        self,
        container_id: str,
        expected_compose_project: str | None = None,
        expected_service_name: str | None = None
    ) -> Any:
        """
        Retrieve and validate a Docker container by its ID.
        Strictly enforces:
        1. Container exists and can be inspected.
        2. Container has generic opt-in label 'faultlab.target=true'.
        3. Container is NOT labeled or named as platform infrastructure ('faultlab.platform=true' or in PROTECTED_SERVICES).
        4. If expected_compose_project is specified, container's compose project must match.
        5. If expected_service_name is specified, container's compose service must match.
        Raises ContainerSecurityError, ContainerNotFoundError, or DockerUnavailableError.
        """
        try:
            container = self.client.containers.get(container_id)
            container.reload()
        except docker.errors.NotFound:
            raise ContainerNotFoundError(f"Container '{container_id}' was not found on the Docker host.")
        except DockerException as e:
            raise DockerUnavailableError(f"Docker API error accessing container '{container_id}': {str(e)}") from e

        labels = container.labels or {}
        c_name = container.name
        c_service = labels.get("com.docker.compose.service", "")
        c_project = labels.get("com.docker.compose.project", "")

        # 1. Platform protection check
        is_platform_labeled = str(labels.get(PLATFORM_LABEL, "")).lower() == "true"
        is_protected_name = c_service.lower() in PROTECTED_SERVICES or any(
            p in c_name.lower() for p in PROTECTED_SERVICES
        )
        if is_platform_labeled or is_protected_name:
            raise ContainerSecurityError(
                f"Container '{c_name}' ({container_id[:12]}) is protected platform infrastructure and cannot be operated on."
            )

        # 2. Opt-in check
        opt_in = str(labels.get(TARGET_OPT_IN_LABEL, "")).lower() == TARGET_OPT_IN_VALUE
        if not opt_in:
            raise ContainerSecurityError(
                f"Container '{c_name}' ({container_id[:12]}) is missing required opt-in label '{TARGET_OPT_IN_LABEL}={TARGET_OPT_IN_VALUE}'."
            )

        # 3. Project check
        if expected_compose_project and c_project != expected_compose_project:
            raise ContainerSecurityError(
                f"Container '{c_name}' belongs to project '{c_project}', expected '{expected_compose_project}'."
            )

        # 4. Service check
        if expected_service_name and c_service != expected_service_name:
            raise ContainerSecurityError(
                f"Container '{c_name}' belongs to service '{c_service}', expected '{expected_service_name}'."
            )

        return container

    def _assert_container_safety(self, container: Any, operation: str) -> None:
        """Enforce safety invariant check on any container before lifecycle modification."""
        labels = container.labels or {}
        c_name = container.name
        c_service = labels.get("com.docker.compose.service", "")

        is_platform = str(labels.get(PLATFORM_LABEL, "")).lower() == "true"
        is_protected = c_service.lower() in PROTECTED_SERVICES or any(
            p in c_name.lower() for p in PROTECTED_SERVICES
        )
        if is_platform or is_protected:
            raise ContainerSecurityError(
                f"Cannot {operation} protected platform infrastructure container '{c_name}'."
            )

        opt_in = str(labels.get(TARGET_OPT_IN_LABEL, "")).lower() == TARGET_OPT_IN_VALUE
        if not opt_in:
            raise ContainerSecurityError(
                f"Cannot {operation} container '{c_name}': missing opt-in label '{TARGET_OPT_IN_LABEL}={TARGET_OPT_IN_VALUE}'."
            )

    def stop_container(self, container: Any, timeout: int = 5) -> None:
        """Safely stop a validated target container."""
        self._assert_container_safety(container, "stop")
        try:
            container.stop(timeout=timeout)
            container.reload()
        except DockerException as e:
            raise DockerUnavailableError(f"Failed to stop container {container.short_id}: {str(e)}") from e

    def start_container(self, container: Any) -> None:
        """Safely start a validated target container."""
        self._assert_container_safety(container, "start")
        try:
            container.start()
            container.reload()
        except DockerException as e:
            raise DockerUnavailableError(f"Failed to start container {container.short_id}: {str(e)}") from e

    def pause_container(self, container: Any) -> None:
        """Safely pause a validated target container."""
        self._assert_container_safety(container, "pause")
        try:
            container.pause()
            container.reload()
        except DockerException as e:
            raise DockerUnavailableError(f"Failed to pause container {container.short_id}: {str(e)}") from e

    def unpause_container(self, container: Any) -> None:
        """Safely unpause a validated target container."""
        self._assert_container_safety(container, "unpause")
        try:
            container.unpause()
            container.reload()
        except DockerException as e:
            raise DockerUnavailableError(f"Failed to unpause container {container.short_id}: {str(e)}") from e


    def inspect_container_state(self, container: Any) -> dict[str, Any]:
        """Inspect fresh container status, health, and attributes."""
        try:
            container.reload()
            state = container.attrs.get("State", {})
            health = state.get("Health", {}).get("Status", "none")
            return {
                "container_id": container.id,
                "container_short_id": container.short_id,
                "container_name": container.name,
                "status": container.status,
                "health": health,
                "running": state.get("Running", False),
                "paused": state.get("Paused", False),
                "restart_count": container.attrs.get("RestartCount", 0),
            }
        except Exception as e:
            return {
                "container_id": getattr(container, "id", "unknown"),
                "status": "unreachable",
                "health": "unknown",
                "error": str(e),
            }

    def get_container_stats(self, container: Any) -> dict[str, Any]:
        """Fetch a single non-streaming snapshot of real container resource stats."""
        try:
            stats = container.stats(stream=False)
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            cpu_usage = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            precpu_usage = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            system_cpu = cpu_stats.get("system_cpu_usage", 0)
            system_precpu = precpu_stats.get("system_cpu_usage", 0)

            cpu_percent = 0.0
            cpu_delta = cpu_usage - precpu_usage
            system_delta = system_cpu - system_precpu
            online_cpus = cpu_stats.get("online_cpus", len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []) or [1]))

            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100.0, 2)

            mem_stats = stats.get("memory_stats", {})
            mem_usage_bytes = mem_stats.get("usage", 0)
            mem_limit_bytes = mem_stats.get("limit", 0)
            mem_percent = 0.0
            if mem_limit_bytes > 0:
                mem_percent = round((mem_usage_bytes / mem_limit_bytes) * 100.0, 2)

            return {
                "available": True,
                "cpu_percent": cpu_percent,
                "memory_usage_bytes": mem_usage_bytes,
                "memory_limit_bytes": mem_limit_bytes,
                "memory_percent": mem_percent,
            }
        except Exception as e:
            return {
                "available": False,
                "reason": f"Stats collection unavailable: {str(e)}"
            }
