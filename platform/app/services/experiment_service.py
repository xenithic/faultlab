import datetime
import logging
import threading
import time
from typing import Any
import requests
from flask import Flask
from ..extensions import db
from ..models import Experiment, RegisteredTarget
from .docker_service import (
    DockerService,
    DockerUnavailableError,
    ContainerSecurityError,
    ContainerNotFoundError,
)

logger = logging.getLogger(__name__)

# Supported and deferred fault types
SUPPORTED_FAULT_TYPES = {"service_failure", "service_pause"}
DEFERRED_FAULT_TYPES = {
    "latency": "Deferred: Requires Toxiproxy sidecar or traffic interceptor in Docker network topology.",
    "resource_stress": "Deferred: Requires 'stress-ng' binary in target container image and cgroup configuration.",
    "http_error": "Deferred: Requires application-level HTTP proxy or interceptor proxy.",
}

# Bounds on duration and timeouts
MIN_DURATION_SECONDS = 1
MAX_DURATION_SECONDS = 300
DEFAULT_DURATION_SECONDS = 10

MIN_STOP_TIMEOUT = 1
MAX_STOP_TIMEOUT = 30
DEFAULT_STOP_TIMEOUT = 5

RECOVERY_VERIFICATION_TIMEOUT = 15.0  # seconds


class ExecutionConflictError(Exception):
    """Raised when an experiment execution conflicts with another running experiment."""
    pass


class ParameterValidationError(Exception):
    """Raised when experiment parameters fail server validation."""
    pass


def validate_experiment_parameters(fault_type: str, parameters: dict[str, Any] | None) -> dict[str, Any]:
    """
    Validate and sanitize experiment parameters on the server.
    Enforces hard limits on duration and intensity.
    """
    params = dict(parameters or {})

    # 1. Validate duration_seconds
    raw_duration = params.get("duration_seconds", DEFAULT_DURATION_SECONDS)
    try:
        duration = float(raw_duration)
    except (ValueError, TypeError):
        raise ParameterValidationError(
            f"'duration_seconds' must be a numeric value, got {raw_duration!r}."
        )

    if duration < MIN_DURATION_SECONDS or duration > MAX_DURATION_SECONDS:
        raise ParameterValidationError(
            f"'duration_seconds' must be between {MIN_DURATION_SECONDS} and {MAX_DURATION_SECONDS} seconds. Received: {duration}."
        )
    params["duration_seconds"] = int(duration) if duration.is_integer() else duration

    # Validate optional recovery_timeout (bounded between 0.1 and 60 seconds)
    raw_recovery_timeout = params.get("recovery_timeout")
    if raw_recovery_timeout is not None:
        try:
            rec_timeout = float(raw_recovery_timeout)
            if 0.1 <= rec_timeout <= 60.0:
                params["recovery_timeout"] = rec_timeout
            else:
                raise ParameterValidationError(
                    f"'recovery_timeout' must be between 0.1 and 60.0 seconds. Received: {rec_timeout}."
                )
        except (ValueError, TypeError):
            raise ParameterValidationError(
                f"'recovery_timeout' must be a numeric value, got {raw_recovery_timeout!r}."
            )

    # 2. Validate fault-specific parameters

    if fault_type == "service_failure":
        raw_timeout = params.get("stop_timeout", DEFAULT_STOP_TIMEOUT)
        try:
            stop_timeout = int(raw_timeout)
        except (ValueError, TypeError):
            raise ParameterValidationError(
                f"'stop_timeout' must be an integer, got {raw_timeout!r}."
            )
        if stop_timeout < MIN_STOP_TIMEOUT or stop_timeout > MAX_STOP_TIMEOUT:
            raise ParameterValidationError(
                f"'stop_timeout' must be between {MIN_STOP_TIMEOUT} and {MAX_STOP_TIMEOUT} seconds. Received: {stop_timeout}."
            )
        params["stop_timeout"] = stop_timeout

    elif fault_type == "service_pause":
        # service_pause needs only duration_seconds
        pass

    return params


def probe_service_http_health(container: Any, service_name: str) -> dict[str, Any]:
    """
    Safely attempt a real HTTP health probe against the target service.
    Returns real measured latency and status code, or records unavailability without fabrication.
    """
    # Service port mapping table for standard target application services
    SERVICE_PORTS = {
        "product-service": 5001,
        "order-service": 5002,
        "inventory-service": 5003,
        "payment-service": 5004,
        "api-gateway": 8000,
    }

    port = SERVICE_PORTS.get(service_name)
    endpoints_to_try = []

    # 1. Check if container has a published host port
    try:
        ports_dict = container.attrs.get("NetworkSettings", {}).get("Ports", {})
        for container_port_spec, host_bindings in ports_dict.items():
            if host_bindings:
                for binding in host_bindings:
                    host_ip = binding.get("HostIp", "127.0.0.1")
                    if host_ip == "0.0.0.0":
                        host_ip = "127.0.0.1"
                    host_port = binding.get("HostPort")
                    if host_port:
                        endpoints_to_try.append(f"http://{host_ip}:{host_port}/health")
    except Exception:
        pass

    # 2. Direct internal service name (works when platform is on the same Docker network)
    if port:
        endpoints_to_try.append(f"http://{service_name}:{port}/health")
        endpoints_to_try.append(f"http://127.0.0.1:{port}/health")

    for url in endpoints_to_try:
        t0 = time.perf_counter()
        try:
            resp = requests.get(url, timeout=1.0)
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return {
                "available": True,
                "url": url,
                "status_code": resp.status_code,
                "latency_ms": latency_ms,
                "is_healthy": resp.status_code == 200,
            }
        except requests.exceptions.RequestException as e:
            # If connection failed, continue to next endpoint or return real failure
            last_err = str(e)
            continue

    return {
        "available": False,
        "reason": "HTTP health endpoint could not be reached from platform environment.",
    }


class ExperimentExecutor:
    """
    Manages experiment execution lifecycles, concurrency safety,
    cancellation signaling, metrics capture, and recovery verification.
    """

    def __init__(self, docker_service: DockerService | None = None):
        self.docker_service = docker_service or DockerService()
        self._lock = threading.Lock()
        # Maps experiment_id -> dict(cancel_event, thread, target_id, container_id)
        self._active_executions: dict[int, dict[str, Any]] = {}

    def is_experiment_running(self, experiment_id: int) -> bool:
        with self._lock:
            return experiment_id in self._active_executions

    def get_active_target_experiment(self, target_id: int) -> int | None:
        """Return experiment_id if an experiment is currently running against target_id."""
        with self._lock:
            for exp_id, ctx in self._active_executions.items():
                if ctx.get("target_id") == target_id:
                    return exp_id
        return None

    def start_experiment(
        self,
        experiment_id: int,
        app: Flask,
        background: bool = True
    ) -> tuple[bool, str | None, dict[str, Any] | None]:
        """
        Validate, bind, and initiate experiment execution.
        Returns (success, error_message, experiment_dict).
        """
        with self._lock:
            # 1. Check duplicate execution on this experiment
            if experiment_id in self._active_executions:
                return False, f"Experiment {experiment_id} is already running.", None

            experiment = db.session.get(Experiment, experiment_id)
            if not experiment:
                return False, f"Experiment with id {experiment_id} not found.", None

            if experiment.status == "running":
                return False, f"Experiment {experiment_id} is already in 'running' status.", None

            if experiment.status in ("completed", "failed", "cancelled", "timed_out"):
                return False, (
                    f"Cannot start experiment with status '{experiment.status}'. "
                    f"Only 'pending' experiments can be started."
                ), None

            # 2. Check concurrency: only one running experiment per target
            active_target_exp = None
            for e_id, ctx in self._active_executions.items():
                if ctx.get("target_id") == experiment.target_id:
                    active_target_exp = e_id
                    break
            if active_target_exp:
                return False, (
                    f"Target {experiment.target_id} already has an active experiment running "
                    f"(Experiment id: {active_target_exp}). Wait for it to finish."
                ), None

            running_db_exp = Experiment.query.filter(
                Experiment.target_id == experiment.target_id,
                Experiment.status == "running",
                Experiment.id != experiment_id
            ).first()
            if running_db_exp:
                return False, (
                    f"Target {experiment.target_id} already has an active experiment running in database "
                    f"(Experiment id: {running_db_exp.id}). Wait for it to finish."
                ), None


            # 3. Check fault type support
            fault_type = experiment.fault_type
            if fault_type not in SUPPORTED_FAULT_TYPES:
                reason = DEFERRED_FAULT_TYPES.get(
                    fault_type,
                    f"Fault type '{fault_type}' is not supported for execution."
                )
                return False, (
                    f"Fault type '{fault_type}' cannot be executed in Milestone 3. "
                    f"{reason} Supported types are: {sorted(SUPPORTED_FAULT_TYPES)}."
                ), None

            # 4. Validate parameters
            try:
                validated_params = validate_experiment_parameters(fault_type, experiment.parameters)
                experiment.parameters = validated_params
            except ParameterValidationError as e:
                return False, f"Parameter validation failed: {str(e)}", None

            # 5. Check target status and authorization
            target = experiment.target
            if not target:
                return False, f"Target associated with experiment {experiment_id} does not exist.", None

            if target.status != "active":
                return False, f"Target '{target.name}' is {target.status}. Only active targets can accept experiments.", None

            if target.validation_status != "valid":
                return False, f"Target '{target.name}' has validation status '{target.validation_status}'. It must be 'valid'.", None

            if experiment.target_service not in (target.allowed_services or []):
                return False, f"Service '{experiment.target_service}' is not in target's allowed_services.", None

            # 6. Revalidate container against fresh live Docker state immediately before execution
            try:
                is_valid, err_msg, container_info = self.docker_service.validate_service_for_experiment(
                    compose_project=target.compose_project,
                    service_name=experiment.target_service,
                    allowed_services=target.allowed_services,
                )
            except DockerUnavailableError as e:
                return False, f"Docker daemon communication error during pre-execution check: {str(e)}", None

            if not is_valid or not container_info:
                return False, f"Pre-execution container validation failed: {err_msg}", None

            live_container_id = container_info.get("container_id")

            # Detect stale or replaced containers
            if experiment.target_container_id and experiment.target_container_id != live_container_id:
                return False, (
                    f"Stale container detected: The container for service '{experiment.target_service}' "
                    f"was replaced since experiment creation. Bound ID was '{experiment.target_container_id}', "
                    f"live container ID is '{live_container_id}'."
                ), None

            # Bind to freshly validated container identity
            experiment.target_container_id = live_container_id
            experiment.status = "running"
            experiment.started_at = datetime.datetime.now(datetime.timezone.utc)
            experiment.error_message = None

            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                return False, f"Database error updating experiment status: {str(e)}", None

            # Setup cancellation and execution context
            cancel_event = threading.Event()
            execution_ctx = {
                "cancel_event": cancel_event,
                "target_id": target.id,
                "container_id": live_container_id,
                "fault_type": fault_type,
                "started_at": experiment.started_at,
            }
            self._active_executions[experiment_id] = execution_ctx

            exp_dict = experiment.to_dict()

        # Execute lifecycle either in background thread or synchronously
        if background:
            thread = threading.Thread(
                target=self._run_lifecycle,
                args=(app, experiment_id, cancel_event),
                name=f"faultlab-exp-{experiment_id}",
                daemon=True,
            )
            execution_ctx["thread"] = thread
            thread.start()
        else:
            self._run_lifecycle(app, experiment_id, cancel_event)
            with app.app_context():
                exp = db.session.get(Experiment, experiment_id)
                exp_dict = exp.to_dict() if exp else exp_dict

        return True, None, exp_dict

    def cancel_experiment(self, experiment_id: int, app: Flask) -> tuple[bool, str, int]:
        """
        Cancel an experiment. Handles both pending and running experiments.
        Returns (success, message, http_status_code).
        """
        with self._lock:
            experiment = db.session.get(Experiment, experiment_id)
            if not experiment:
                return False, f"Experiment with id {experiment_id} not found.", 404

            # If pending: cancel directly
            if experiment.status == "pending":
                experiment.status = "cancelled"
                experiment.error_message = "Experiment was cancelled by user while pending."
                experiment.ended_at = datetime.datetime.now(datetime.timezone.utc)
                try:
                    db.session.commit()
                    return True, f"Pending experiment {experiment_id} cancelled successfully.", 200
                except Exception as e:
                    db.session.rollback()
                    return False, f"Database error cancelling experiment: {str(e)}", 500

            # If running: signal cancellation to active execution context
            if experiment.status == "running":
                ctx = self._active_executions.get(experiment_id)
                if ctx and "cancel_event" in ctx:
                    ctx["cancel_event"].set()
                    return True, f"Cancellation requested for running experiment {experiment_id}. Recovery initiated.", 200
                else:
                    # Running in DB but no active execution context (e.g. platform restart)
                    experiment.status = "cancelled"
                    experiment.error_message = "Running experiment cancelled (no active executor thread found)."
                    experiment.ended_at = datetime.datetime.now(datetime.timezone.utc)
                    db.session.commit()
                    return True, f"Orphaned running experiment {experiment_id} marked cancelled.", 200

            return False, (
                f"Cannot cancel experiment with status '{experiment.status}'. "
                f"Only 'pending' experiments can be cancelled (or 'running' to trigger recovery)."
            ), 400


    def _run_lifecycle(self, app: Flask, experiment_id: int, cancel_event: threading.Event) -> None:
        """
        Complete lifecycle execution flow:
        INJECT → OBSERVE → MEASURE → RECOVER → VERIFY
        Guarantees cleanup on every exit path.
        """
        with app.app_context():
            experiment = db.session.get(Experiment, experiment_id)
            if not experiment:
                logger.error("Experiment %d not found in execution thread.", experiment_id)
                with self._lock:
                    self._active_executions.pop(experiment_id, None)
                return

            target = experiment.target
            fault_type = experiment.fault_type
            parameters = experiment.parameters or {}
            duration_seconds = parameters.get("duration_seconds", DEFAULT_DURATION_SECONDS)
            stop_timeout = parameters.get("stop_timeout", DEFAULT_STOP_TIMEOUT)

            result_metrics: dict[str, Any] = {
                "before": {},
                "during": {},
                "after": {},
                "recovery_verification": {},
                "cleanup": {"success": True, "error": None},
            }

            container = None
            is_paused = False
            is_stopped = False
            execution_error = None
            cleanup_error = None

            try:
                # 1. Retrieve validated container object
                container = self.docker_service.get_validated_container(
                    container_id=experiment.target_container_id,
                    expected_compose_project=target.compose_project,
                    expected_service_name=experiment.target_service,
                )

                # 2. Capture Baseline Observations (Before fault)
                state_before = self.docker_service.inspect_container_state(container)
                stats_before = self.docker_service.get_container_stats(container)
                http_before = probe_service_http_health(container, experiment.target_service)

                result_metrics["before"] = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "container_state": state_before,
                    "container_stats": stats_before,
                    "http_health": http_before,
                }
                experiment.baseline_metrics = result_metrics["before"]
                db.session.commit()

                # Check if cancellation was requested before injection
                if cancel_event.is_set():
                    raise InterruptedError("Experiment was cancelled prior to fault injection.")

                # 3. Inject Fault
                logger.info(
                    "Injecting %s into %s (container %s) for %ss",
                    fault_type, experiment.target_service, container.short_id, duration_seconds
                )

                if fault_type == "service_pause":
                    self.docker_service.pause_container(container)
                    is_paused = True
                elif fault_type == "service_failure":
                    self.docker_service.stop_container(container, timeout=stop_timeout)
                    is_stopped = True
                else:
                    raise ValueError(f"Unsupported fault type: {fault_type}")

                # 4. Capture Observations During Fault
                state_during = self.docker_service.inspect_container_state(container)
                http_during = probe_service_http_health(container, experiment.target_service)
                result_metrics["during"] = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "container_state": state_during,
                    "http_health": http_during,
                }
                experiment.result_metrics = result_metrics
                db.session.commit()

                # 5. Wait for duration or cancellation signal
                was_cancelled = cancel_event.wait(timeout=duration_seconds)
                if was_cancelled:
                    logger.info("Experiment %d cancelled by user during fault wait.", experiment_id)

            except Exception as e:
                execution_error = str(e)
                logger.error("Error during experiment %d execution: %s", experiment_id, execution_error)

            finally:
                # 6. Cleanup & Recovery - GUARANTEED EXECUTION PATH
                logger.info("Executing recovery/cleanup for experiment %d", experiment_id)
                recovery_start_time = time.perf_counter()

                if container is not None:
                    # Guarantee unpause
                    if is_paused:
                        try:
                            self.docker_service.unpause_container(container)
                            logger.info("Successfully unpaused container %s", container.short_id)
                        except Exception as e:
                            cleanup_error = f"Failed to unpause container: {str(e)}"
                            logger.error("Cleanup error unpausing container %s: %s", container.short_id, cleanup_error)

                    # Guarantee start
                    if is_stopped:
                        try:
                            self.docker_service.start_container(container)
                            logger.info("Successfully restarted container %s", container.short_id)
                        except Exception as e:
                            cleanup_error = f"Failed to restart stopped container: {str(e)}"
                            logger.error("Cleanup error starting container %s: %s", container.short_id, cleanup_error)

                result_metrics["cleanup"]["success"] = (cleanup_error is None)
                result_metrics["cleanup"]["error"] = cleanup_error

                # 7. Recovery Verification & Measurement
                recovery_verified = False
                recovery_status = "unverified"
                recovery_time_seconds = None
                evidence = "No recovery check performed."

                if container is not None and cleanup_error is None:
                    # Poll container status until healthy/running or verification timeout
                    recovery_timeout = float(parameters.get("recovery_timeout", RECOVERY_VERIFICATION_TIMEOUT))
                    deadline = time.perf_counter() + recovery_timeout
                    while time.perf_counter() < deadline:

                        try:
                            container.reload()
                            state_now = self.docker_service.inspect_container_state(container)
                            health_status = state_now.get("health", "none")
                            is_running = state_now.get("status") == "running"

                            if is_running:
                                elapsed = round(time.perf_counter() - recovery_start_time, 2)
                                if health_status == "healthy":
                                    recovery_verified = True
                                    recovery_status = "verified"
                                    recovery_time_seconds = elapsed
                                    evidence = (
                                        f"Container status returned to 'running' and healthcheck reported 'healthy' "
                                        f"in {elapsed}s."
                                    )
                                    break
                                elif health_status in ("none", ""):
                                    # Container has no configured docker healthcheck; check HTTP probe
                                    http_check = probe_service_http_health(container, experiment.target_service)
                                    if http_check.get("available") and http_check.get("status_code") == 200:
                                        recovery_verified = True
                                        recovery_status = "verified"
                                        recovery_time_seconds = elapsed
                                        evidence = (
                                            f"Container status returned to 'running' and HTTP health check passed (200 OK) "
                                            f"in {elapsed}s."
                                        )
                                        break
                                    else:
                                        # Container is running, HTTP probe unmapped or starting
                                        recovery_status = "unverified"
                                        recovery_time_seconds = elapsed
                                        evidence = (
                                            f"Container status is 'running' after {elapsed}s, but healthcheck is "
                                            f"unconfigured or HTTP probe could not verify application readiness."
                                        )
                                        break
                        except Exception as reload_err:
                            logger.warning("Error inspecting container during recovery: %s", reload_err)

                        time.sleep(0.5)

                    if not recovery_verified and recovery_status != "unverified":
                        recovery_status = "failed"
                        evidence = f"Container did not recover to a healthy running state within {RECOVERY_VERIFICATION_TIMEOUT}s."
                else:
                    recovery_status = "failed"
                    evidence = f"Recovery failed due to cleanup or container error: {cleanup_error or execution_error}"

                # Capture After observations
                state_after = self.docker_service.inspect_container_state(container) if container else {}
                http_after = probe_service_http_health(container, experiment.target_service) if container else {}
                result_metrics["after"] = {
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "container_state": state_after,
                    "http_health": http_after,
                }

                result_metrics["recovery_verification"] = {
                    "status": recovery_status,
                    "verified": recovery_verified,
                    "recovery_time_seconds": recovery_time_seconds,
                    "evidence": evidence,
                }

                # 8. Record Final Experiment State
                experiment.ended_at = datetime.datetime.now(datetime.timezone.utc)
                experiment.recovery_time_seconds = recovery_time_seconds
                experiment.result_metrics = result_metrics

                if cancel_event.is_set():
                    experiment.status = "cancelled"
                    experiment.error_message = execution_error or "Experiment was cancelled by user."
                elif execution_error or cleanup_error or recovery_status in ("failed", "unverified"):
                    experiment.status = "failed"
                    experiment.error_message = (
                        cleanup_error or execution_error
                        or f"Recovery verification {recovery_status}: {evidence}"
                    )
                else:
                    experiment.status = "completed"
                    experiment.error_message = None

                try:
                    db.session.commit()
                except Exception as db_err:
                    logger.error("Failed to persist final experiment state: %s", db_err)
                    db.session.rollback()

                # Clean up active execution registry
                with self._lock:
                    self._active_executions.pop(experiment_id, None)


# Global executor instance
executor = ExperimentExecutor()


def reconcile_orphaned_experiments(app: Flask) -> None:
    """
    Safely reconciles any experiments that were marked 'running' when the platform
    server was terminated or restarted.
    Only modifies a container when persisted evidence in the experiment record confirms
    FaultLab successfully injected a fault into that exact container before restarting.
    Does not blindly start containers that may have been intentionally stopped externally.
    """
    with app.app_context():
        orphans = Experiment.query.filter_by(status="running").all()
        if not orphans:
            return

        logger.warning("Found %d orphaned 'running' experiments on platform startup.", len(orphans))
        docker_service = DockerService()
        docker_available = docker_service.is_available()

        for exp in orphans:
            recovery_notes = []
            if docker_available and exp.target_container_id:
                try:
                    target = exp.target
                    container = docker_service.get_validated_container(
                        container_id=exp.target_container_id,
                        expected_compose_project=target.compose_project if target else None,
                        expected_service_name=exp.target_service,
                    )
                    state = docker_service.inspect_container_state(container)

                    # Persisted evidence verification: FaultLab must have recorded active
                    # fault injection ('during' observations) on this exact container
                    has_persisted_fault_evidence = bool(
                        exp.result_metrics and exp.result_metrics.get("during")
                    )

                    if not has_persisted_fault_evidence:
                        recovery_notes.append(
                            "No persisted evidence of active fault injection prior to restart; container left unmodified."
                        )
                    elif exp.fault_type == "service_pause" and state.get("paused"):
                        docker_service.unpause_container(container)
                        recovery_notes.append("Unpaused orphaned paused container based on persisted fault evidence.")
                    elif exp.fault_type == "service_failure" and not state.get("running"):
                        docker_service.start_container(container)
                        recovery_notes.append("Restarted orphaned stopped container based on persisted fault evidence.")
                    else:
                        recovery_notes.append(f"Container was already in state: {state.get('status')}.")
                except Exception as e:
                    recovery_notes.append(f"Automatic container recovery failed: {str(e)}")
            else:
                recovery_notes.append("Docker unavailable or container ID missing; container state unverified.")

            exp.status = "failed"
            exp.ended_at = datetime.datetime.now(datetime.timezone.utc)
            note_str = " | ".join(recovery_notes)
            exp.error_message = (
                f"Platform server was restarted while this experiment was running. "
                f"Reconciliation: {note_str}"
            )


        try:
            db.session.commit()
            logger.info("Successfully reconciled %d orphaned experiments.", len(orphans))
        except Exception as e:
            db.session.rollback()
            logger.error("Failed to commit orphaned experiments reconciliation: %s", e)
