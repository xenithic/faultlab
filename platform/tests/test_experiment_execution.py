from unittest.mock import MagicMock, patch
import pytest
from app import create_app, db
from app.models import RegisteredTarget, Experiment
from app.services import (
    DockerService,
    ExperimentExecutor,
    reconcile_orphaned_experiments,
)
from app.services.docker_service import TARGET_OPT_IN_LABEL, PLATFORM_LABEL


def create_mock_container(
    name: str = "order-1",
    service: str = "order-service",
    project: str = "test-proj",
    status: str = "running",
    opt_in: bool = True,
    is_platform: bool = False,
    health: str = "healthy",
    cid: str = "cid_1234567890abcdef",
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
            "Running": (status == "running"),
            "Paused": (status == "paused"),
            "Health": {"Status": health},
        },
        "RestartCount": 0,
        "NetworkSettings": {"Ports": {}},
    }
    container.stats.return_value = {
        "cpu_stats": {"cpu_usage": {"total_usage": 500000}, "system_cpu_usage": 10000000},
        "precpu_stats": {"cpu_usage": {"total_usage": 400000}, "system_cpu_usage": 9000000},
        "memory_stats": {"usage": 52428800, "limit": 1073741824},
    }

    def _mock_pause():
        container.status = "paused"
        container.attrs["State"]["Running"] = True
        container.attrs["State"]["Paused"] = True

    def _mock_unpause():
        container.status = "running"
        container.attrs["State"]["Running"] = True
        container.attrs["State"]["Paused"] = False

    def _mock_stop(*args, **kwargs):
        container.status = "exited"
        container.attrs["State"]["Running"] = False
        container.attrs["State"]["Paused"] = False
        container.attrs["State"]["ExitCode"] = 0

    def _mock_start(*args, **kwargs):
        container.status = "running"
        container.attrs["State"]["Running"] = True
        container.attrs["State"]["Paused"] = False
        container.attrs["State"]["ExitCode"] = 0

    container.pause.side_effect = _mock_pause
    container.unpause.side_effect = _mock_unpause
    container.stop.side_effect = _mock_stop
    container.start.side_effect = _mock_start

    return container


@pytest.fixture(autouse=True)
def mock_http_probe():
    """Mock HTTP health and traffic probing so tests run instantly without real network delays."""
    with patch("app.services.experiment_service.probe_service_http_health") as mock_health, \
         patch("app.services.experiment_service.probe_service_traffic") as mock_traffic:
        mock_health.return_value = {
            "available": True,
            "url": "http://127.0.0.1:5002/health",
            "status_code": 200,
            "latency_ms": 12.5,
            "is_healthy": True,
        }
        mock_traffic.return_value = {
            "available": True,
            "url": "http://127.0.0.1:5002/orders",
            "path": "/orders",
            "status_code": 200,
            "latency_ms": 12.5,
            "is_healthy": True,
        }
        yield (mock_health, mock_traffic)


@pytest.fixture
def app_instance():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.rollback()
        db.drop_all()


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def setup_target_and_experiment(
    fault_type: str = "service_pause",
    duration: int = 1,
    service: str = "order-service",
    cid: str = "cid_1234567890abcdef",
):
    target = RegisteredTarget(
        name="test-target",
        compose_project="test-proj",
        allowed_services=["order-service", "product-service"],
        validation_status="valid",
        status="active",
    )
    db.session.add(target)
    db.session.commit()

    experiment = Experiment(
        target_id=target.id,
        fault_type=fault_type,
        target_service=service,
        target_container_id=cid,
        parameters={"duration_seconds": duration},
        status="pending",
    )
    db.session.add(experiment)
    db.session.commit()
    return target, experiment


def test_service_pause_lifecycle_success(app_instance):
    """Test full execution of service_pause: pending -> running -> completed."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, exp_data = custom_executor.start_experiment(
        experiment_id=experiment.id,
        app=app_instance,
        background=False,  # Run synchronously for test verification
    )

    assert success is True
    assert err is None

    # Verify Docker API pause and unpause calls
    mock_c.pause.assert_called_once()
    mock_c.unpause.assert_called_once()

    # Verify DB state
    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.started_at is not None
    assert exp.ended_at is not None
    assert exp.recovery_time_seconds is not None
    assert exp.result_metrics is not None
    assert exp.result_metrics["recovery_verification"]["status"] == "verified"
    assert exp.result_metrics["recovery_verification"]["verified"] is True
    assert exp.result_metrics["cleanup"]["success"] is True


def test_service_failure_lifecycle_success(app_instance):
    """Test full execution of service_failure: stop -> wait -> start -> verify."""
    target, experiment = setup_target_and_experiment(fault_type="service_failure", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, exp_data = custom_executor.start_experiment(
        experiment_id=experiment.id,
        app=app_instance,
        background=False,
    )

    assert success is True
    assert err is None

    # Verify Docker API stop and start calls
    mock_c.stop.assert_called_once_with(timeout=5)
    mock_c.start.assert_called_once()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.result_metrics["recovery_verification"]["status"] == "verified"


def test_guaranteed_unpause_on_fault_error(app_instance):
    """Guarantees unpause is attempted even if an exception occurs during the fault."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)

    # Raise exception specifically during fault wait/observation
    call_count = [0]
    original_inspect = docker_svc.inspect_container_state

    def inspect_with_failure(c):
        call_count[0] += 1
        if call_count[0] == 2:  # 2nd call is during fault observation
            raise RuntimeError("Simulated crash during fault injection observation")
        return original_inspect(c)

    docker_svc.inspect_container_state = inspect_with_failure
    custom_executor = ExperimentExecutor(docker_service=docker_svc)
    custom_executor.start_experiment(experiment.id, app_instance, background=False)

    # Even though inspect crashed during fault, unpause must still be called in cleanup!
    mock_c.pause.assert_called_once()
    mock_c.unpause.assert_called_once()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert "Simulated crash during fault injection observation" in exp.error_message


def test_duplicate_start_prevention(app_instance):
    """Prevent starting an already running experiment or completed experiment."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    # Mark as running in active executions
    custom_executor._active_executions[experiment.id] = {"target_id": target.id}

    success, err, _ = custom_executor.start_experiment(experiment.id, app_instance)
    assert success is False
    assert "already running" in err


def test_concurrent_target_experiment_prevention(app_instance):
    """Prevent starting two experiments on the same target simultaneously."""
    target, exp1 = setup_target_and_experiment(fault_type="service_pause", duration=1)

    exp2 = Experiment(
        target_id=target.id,
        fault_type="service_failure",
        target_service="product-service",
        target_container_id="cid_prod_999",
        parameters={"duration_seconds": 1},
        status="pending",
    )
    db.session.add(exp2)
    db.session.commit()

    docker_svc = DockerService(client=MagicMock())
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    # Mark exp1 as active on target
    custom_executor._active_executions[exp1.id] = {"target_id": target.id}

    success, err, _ = custom_executor.start_experiment(exp2.id, app_instance)
    assert success is False
    assert "already has an active experiment running" in err


def test_parameter_validation_bounds(app_instance):
    """Test duration limits: < 1 and > 300 are rejected."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=500)

    docker_svc = DockerService(client=MagicMock())
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, _ = custom_executor.start_experiment(experiment.id, app_instance)
    assert success is False
    assert "must be between 1 and 300 seconds" in err


def test_stale_replaced_container_detection(app_instance):
    """Detect when the bound container ID does not match the live container ID."""
    target, experiment = setup_target_and_experiment(cid="old_stale_cid_111")
    # Live container has different ID
    live_c = create_mock_container(cid="new_recreated_cid_222")

    mock_client = MagicMock()
    mock_client.containers.list.return_value = [live_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, _ = custom_executor.start_experiment(experiment.id, app_instance)
    assert success is False
    assert "Stale container detected" in err


def test_unsupported_fault_type_rejected_on_start(app_instance):
    """Ensure unsupported fault types return structured rejection."""
    target, experiment = setup_target_and_experiment(fault_type="unsupported_chaos_type")

    docker_svc = DockerService(client=MagicMock())
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, _ = custom_executor.start_experiment(experiment.id, app_instance)
    assert success is False
    assert "Fault type 'unsupported_chaos_type' cannot be executed" in err
    assert "Supported types are" in err


def test_running_experiment_cancellation(app_instance):
    """Test cancelling an actively running experiment."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=5)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    # Start experiment in background thread
    success, err, _ = custom_executor.start_experiment(experiment.id, app_instance, background=True)
    assert success is True

    # Capture background thread reference
    ctx = custom_executor._active_executions.get(experiment.id)
    thread = ctx["thread"]

    # Wait until container has entered fault injection
    import time
    for _ in range(50):
        if mock_c.pause.called:
            break
        time.sleep(0.02)
    assert mock_c.pause.called

    # Cancel it during active fault wait
    ok, msg, code = custom_executor.cancel_experiment(experiment.id, app_instance)
    assert ok is True
    assert code == 200
    assert "Recovery initiated" in msg


    # Join the thread to ensure it finished cleanup
    thread.join(timeout=5)

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "cancelled"
    mock_c.unpause.assert_called()


def test_orphaned_experiments_reconciliation(app_instance):
    """Platform restart reconciliation unpauses orphaned container when persisted fault evidence exists."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause")
    experiment.status = "running"
    experiment.result_metrics = {"during": {"timestamp": "2026-10-21T00:00:00Z"}}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id, status="paused")

    with patch.object(DockerService, "is_available", return_value=True), \
         patch.object(DockerService, "get_validated_container", return_value=mock_c), \
         patch.object(DockerService, "unpause_container") as mock_unpause:
        reconcile_orphaned_experiments(app_instance)
        mock_unpause.assert_called_once_with(mock_c)

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert "Platform server was restarted while this experiment was running" in exp.error_message


def test_orphaned_experiments_reconciliation_skips_without_persisted_evidence(app_instance):
    """Reconciliation leaves container untouched if FaultLab never recorded active fault injection before restart."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause")
    experiment.status = "running"
    # No 'during' metrics persisted (e.g. platform crashed during baseline measurement)
    experiment.result_metrics = {"before": {"container_state": {"status": "running"}}}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id, status="paused")

    with patch.object(DockerService, "is_available", return_value=True), \
         patch.object(DockerService, "get_validated_container", return_value=mock_c), \
         patch.object(DockerService, "unpause_container") as mock_unpause:
        reconcile_orphaned_experiments(app_instance)
        # unpause must NOT be called without persisted evidence!
        mock_unpause.assert_not_called()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert "container left unmodified" in exp.error_message


def test_unverified_recovery_marks_failed_not_completed(app_instance):
    """When recovery verification cannot confirm health, experiment status must be 'failed', never 'completed'."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    experiment.parameters = {"duration_seconds": 1, "recovery_timeout": 0.5}
    db.session.commit()
    mock_c = create_mock_container(cid=experiment.target_container_id)


    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)

    # In recovery inspection, container is running but health status is "starting" (unverified)
    original_inspect = docker_svc.inspect_container_state

    def inspect_with_starting_health(c):
        res = original_inspect(c)
        res["health"] = "starting"
        return res

    docker_svc.inspect_container_state = inspect_with_starting_health
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    with patch("app.services.experiment_service.probe_service_http_health", return_value={"available": False, "reason": "unreachable"}):
        success, err, _ = custom_executor.start_experiment(experiment.id, app_instance, background=False)

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert exp.result_metrics["recovery_verification"]["status"] == "unverified"
    assert "Recovery verification unverified" in exp.error_message


def test_api_start_endpoint_success(client):

    """Test POST /api/experiments/<id>/start via HTTP API."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    with patch("app.services.docker_service.get_docker_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_c
        mock_client.containers.list.return_value = [mock_c]
        mock_get_client.return_value = mock_client

        resp = client.post(f"/api/experiments/{experiment.id}/start?wait=true")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["experiment"]["status"] == "completed"
        assert data["experiment"]["recovery_time_seconds"] is not None


def test_api_start_endpoint_conflict_already_running(client):
    """Test POST /api/experiments/<id>/start returns 409 if already running."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=5)
    from app.services import executor
    executor._active_executions[experiment.id] = {"target_id": target.id}

    resp = client.post(f"/api/experiments/{experiment.id}/start")
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "Conflict"

    # Clean up
    executor._active_executions.pop(experiment.id, None)


def test_api_create_experiment_parameter_validation_error(client):
    """Test POST /api/experiments rejects parameters with duration > 300."""
    target = RegisteredTarget(
        name="target-validation",
        compose_project="proj-val",
        allowed_services=["order-service"],
        validation_status="valid",
        status="active",
    )
    db.session.add(target)
    db.session.commit()

    resp = client.post("/api/experiments", json={
        "target_id": target.id,
        "fault_type": "service_pause",
        "target_service": "order-service",
        "parameters": {"duration_seconds": 999}
    })
    assert resp.status_code == 400
    assert "must be between 1 and 300 seconds" in resp.get_json()["message"]


def test_latency_experiment_lifecycle_execution(app_instance):
    """Test full lifecycle for latency injection: validate, baseline, inject, observe, recover, verify."""
    target, experiment = setup_target_and_experiment(
        fault_type="latency",
        duration=1,
    )
    experiment.parameters = {"duration_seconds": 1, "latency_ms": 300}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    with patch.object(docker_svc, "inject_http_fault", return_value={"active": True}) as mock_inject, \
         patch.object(docker_svc, "remove_http_fault", return_value={"active": False}) as mock_remove:

        success, err, exp_data = custom_executor.start_experiment(experiment.id, app_instance, background=False)
        assert success is True
        mock_inject.assert_called_once()
        mock_remove.assert_called_once()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.recovery_time_seconds is not None
    assert exp.result_metrics["cleanup"]["success"] is True
    assert exp.result_metrics["recovery_verification"]["verified"] is True
    assert "latency" in exp.result_metrics["recovery_verification"]["evidence"].lower()


def test_http_error_experiment_lifecycle_execution(app_instance):
    """Test full lifecycle for HTTP error injection."""
    target, experiment = setup_target_and_experiment(
        fault_type="http_error",
        duration=1,
    )
    experiment.parameters = {"duration_seconds": 1, "error_code": 503, "error_rate": 1.0}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    with patch.object(docker_svc, "inject_http_fault", return_value={"active": True}) as mock_inject, \
         patch.object(docker_svc, "remove_http_fault", return_value={"active": False}) as mock_remove:

        success, err, exp_data = custom_executor.start_experiment(experiment.id, app_instance, background=False)
        assert success is True
        mock_inject.assert_called_once()
        mock_remove.assert_called_once()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.result_metrics["recovery_verification"]["verified"] is True
    assert "HTTP 503" in exp.result_metrics["recovery_verification"]["evidence"]


def test_resource_stress_experiment_lifecycle_execution(app_instance):
    """Test full lifecycle for CPU/Memory resource stress injection."""
    target, experiment = setup_target_and_experiment(
        fault_type="resource_stress",
        duration=1,
    )
    experiment.parameters = {
        "duration_seconds": 1,
        "stress_type": "cpu",
        "cpu_workers": 2,
        "cpu_load": 75,
    }
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    with patch.object(docker_svc, "inject_resource_stress", return_value={"started": True, "tool": "stress-ng"}) as mock_stress, \
         patch.object(docker_svc, "stop_resource_stress") as mock_stop_stress, \
         patch.object(docker_svc, "verify_resource_stress_stopped", return_value=True) as mock_verify_stopped:

        success, err, exp_data = custom_executor.start_experiment(experiment.id, app_instance, background=False)
        assert success is True
        mock_stress.assert_called_once()
        mock_stop_stress.assert_called_once()
        mock_verify_stopped.assert_called()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.result_metrics["recovery_verification"]["verified"] is True
    assert "Stress processes terminated" in exp.result_metrics["recovery_verification"]["evidence"]


def test_resource_stress_cleanup_failure_marks_experiment_failed(app_instance):
    """When stress processes cannot be verified stopped, experiment must be marked failed."""
    target, experiment = setup_target_and_experiment(
        fault_type="resource_stress",
        duration=1,
    )
    experiment.parameters = {"duration_seconds": 1, "stress_type": "cpu"}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)
    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    with patch.object(docker_svc, "inject_resource_stress", return_value={"started": True}), \
         patch.object(docker_svc, "stop_resource_stress"), \
         patch.object(docker_svc, "verify_resource_stress_stopped", return_value=False):

        success, err, exp_data = custom_executor.start_experiment(experiment.id, app_instance, background=False)

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert exp.result_metrics["cleanup"]["success"] is False
    assert "Stress processes failed to terminate" in exp.error_message


def test_parameter_validation_bounds():
    """Verify server-side validation bounds for latency, http_error, and resource_stress."""
    from app.services.experiment_service import validate_experiment_parameters, ParameterValidationError

    # 1. Latency bounds
    valid_lat = validate_experiment_parameters("latency", {"latency_ms": 250, "duration_seconds": 15})
    assert valid_lat["latency_ms"] == 250
    assert valid_lat["duration_seconds"] == 15

    with pytest.raises(ParameterValidationError, match="latency_ms"):
        validate_experiment_parameters("latency", {"latency_ms": 5})  # below min 10ms

    with pytest.raises(ParameterValidationError, match="latency_ms"):
        validate_experiment_parameters("latency", {"latency_ms": 50000})  # above max 10000ms

    # 2. HTTP error bounds
    valid_http = validate_experiment_parameters("http_error", {"error_code": 502, "error_rate": 0.5})
    assert valid_http["error_code"] == 502
    assert valid_http["error_rate"] == 0.5

    with pytest.raises(ParameterValidationError, match="error_code"):
        validate_experiment_parameters("http_error", {"error_code": 200})  # not an error code

    with pytest.raises(ParameterValidationError, match="error_rate"):
        validate_experiment_parameters("http_error", {"error_rate": 0.0})  # below min

    # 3. Resource stress bounds
    valid_stress = validate_experiment_parameters(
        "resource_stress",
        {"stress_type": "both", "cpu_workers": 2, "cpu_load": 90, "memory_workers": 1, "memory_bytes": "256M"}
    )
    assert valid_stress["stress_type"] == "both"
    assert valid_stress["cpu_workers"] == 2
    assert valid_stress["cpu_load"] == 90

    with pytest.raises(ParameterValidationError, match="stress_type"):
        validate_experiment_parameters("resource_stress", {"stress_type": "disk_burn"})

    with pytest.raises(ParameterValidationError, match="cpu_workers"):
        validate_experiment_parameters("resource_stress", {"cpu_workers": 10})  # max is 4

    with pytest.raises(ParameterValidationError, match="cpu_load"):
        validate_experiment_parameters("resource_stress", {"cpu_load": 150})  # max is 100


def test_orphaned_resource_stress_reconciliation(app_instance):
    """Reconciliation safely terminates stress processes when persisted fault evidence exists."""
    target, experiment = setup_target_and_experiment(fault_type="resource_stress")
    experiment.status = "running"
    experiment.result_metrics = {"during": {"timestamp": "2026-10-21T00:00:00Z"}}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)

    with patch.object(DockerService, "is_available", return_value=True), \
         patch.object(DockerService, "get_validated_container", return_value=mock_c), \
         patch.object(DockerService, "stop_resource_stress") as mock_stop:
        reconcile_orphaned_experiments(app_instance)
        mock_stop.assert_called_once_with(mock_c)

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert "Terminated orphaned resource stress" in exp.error_message


def test_orphaned_http_fault_reconciliation(app_instance):
    """Reconciliation safely clears HTTP/latency fault when persisted fault evidence exists."""
    target, experiment = setup_target_and_experiment(fault_type="latency")
    experiment.status = "running"
    experiment.result_metrics = {"during": {"timestamp": "2026-10-21T00:00:00Z"}}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)

    with patch.object(DockerService, "is_available", return_value=True), \
         patch.object(DockerService, "get_validated_container", return_value=mock_c), \
         patch.object(DockerService, "remove_http_fault") as mock_remove:
        reconcile_orphaned_experiments(app_instance)
        mock_remove.assert_called_once_with(mock_c, experiment.target_service)

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "failed"
    assert "Cleared orphaned HTTP/network fault" in exp.error_message


# ===========================================================================
# Recovery Verification Regression Tests
# ===========================================================================

def test_recovery_verification_paused_container_success(app_instance):
    """Regression: service_pause pauses container, unpauses via Docker unpause, and verifies recovery via HTTP probe."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, exp_data = custom_executor.start_experiment(
        experiment_id=experiment.id,
        app=app_instance,
        background=False,
    )

    assert success is True
    assert err is None
    # Semantic verification: unpause must be called; start must not be called
    mock_c.pause.assert_called_once()
    mock_c.unpause.assert_called_once()
    mock_c.start.assert_not_called()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.recovery_time_seconds is not None
    assert exp.result_metrics["recovery_verification"]["status"] == "verified"
    assert exp.result_metrics["recovery_verification"]["verified"] is True
    assert "resumed to 'running' state" in exp.result_metrics["recovery_verification"]["evidence"]


def test_recovery_verification_stopped_container_success(app_instance):
    """Regression: service_failure stops container, restarts via Docker start, and verifies recovery via HTTP probe."""
    target, experiment = setup_target_and_experiment(fault_type="service_failure", duration=1)
    mock_c = create_mock_container(cid=experiment.target_container_id)

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, exp_data = custom_executor.start_experiment(
        experiment_id=experiment.id,
        app=app_instance,
        background=False,
    )

    assert success is True
    assert err is None
    # Semantic verification: start must be called; unpause must not be called
    mock_c.stop.assert_called_once()
    mock_c.start.assert_called_once()
    mock_c.unpause.assert_not_called()

    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    assert exp.status == "completed"
    assert exp.recovery_time_seconds is not None
    assert exp.result_metrics["recovery_verification"]["status"] == "verified"
    assert exp.result_metrics["recovery_verification"]["verified"] is True


def test_recovery_verification_unsuccessful_remains_paused(app_instance):
    """Regression: If container unpause fails or container remains paused, recovery verification must fail."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    experiment.parameters = {"recovery_timeout": 0.5, "duration_seconds": 1}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)
    # Simulate unpause failing to restore running state (remains paused)
    mock_c.unpause.side_effect = lambda: None

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, exp_data = custom_executor.start_experiment(
        experiment_id=experiment.id,
        app=app_instance,
        background=False,
    )

    assert success is True
    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    # Must fail, NOT complete
    assert exp.status == "failed"
    assert exp.recovery_time_seconds is None
    assert exp.result_metrics["recovery_verification"]["status"] == "failed"
    assert exp.result_metrics["recovery_verification"]["verified"] is False
    assert "remained in 'paused' state" in exp.error_message


def test_recovery_verification_unsuccessful_remains_stopped(app_instance):
    """Regression: If container fails to restart and remains exited, recovery verification must fail."""
    target, experiment = setup_target_and_experiment(fault_type="service_failure", duration=1)
    experiment.parameters = {"recovery_timeout": 0.5, "duration_seconds": 1}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id)
    # Simulate start failing to restore running state (remains exited)
    mock_c.start.side_effect = lambda *args, **kwargs: None

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    success, err, exp_data = custom_executor.start_experiment(
        experiment_id=experiment.id,
        app=app_instance,
        background=False,
    )

    assert success is True
    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    # Must fail, NOT complete
    assert exp.status == "failed"
    assert exp.recovery_time_seconds is None
    assert exp.result_metrics["recovery_verification"]["status"] == "failed"
    assert exp.result_metrics["recovery_verification"]["verified"] is False
    assert ("service did not restart" in exp.error_message) or ("exited" in exp.error_message)


def test_recovery_verification_running_but_not_responding(app_instance):
    """Regression: Container is running in Docker, but service HTTP probe returns unhealthy. Must NOT be marked recovered."""
    target, experiment = setup_target_and_experiment(fault_type="service_pause", duration=1)
    experiment.parameters = {"recovery_timeout": 0.5, "duration_seconds": 1}
    db.session.commit()

    mock_c = create_mock_container(cid=experiment.target_container_id, health="none")

    mock_client = MagicMock()
    mock_client.containers.get.return_value = mock_c
    mock_client.containers.list.return_value = [mock_c]

    docker_svc = DockerService(client=mock_client)
    custom_executor = ExperimentExecutor(docker_service=docker_svc)

    # HTTP health check probe returns 503 unhealthy
    with patch("app.services.experiment_service.probe_service_http_health") as mock_health:
        mock_health.return_value = {
            "available": True,
            "status_code": 503,
            "is_healthy": False,
            "reason": "Service Unavailable",
        }

        success, err, exp_data = custom_executor.start_experiment(
            experiment_id=experiment.id,
            app=app_instance,
            background=False,
        )

    assert success is True
    db.session.expire_all()
    exp = db.session.get(Experiment, experiment.id)
    # Must fail, NOT complete
    assert exp.status == "failed"
    assert exp.recovery_time_seconds is None
    assert exp.result_metrics["recovery_verification"]["status"] == "failed"
    assert exp.result_metrics["recovery_verification"]["verified"] is False
    assert "HTTP health probe failed" in exp.error_message

