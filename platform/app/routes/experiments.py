from flask import Blueprint, current_app, jsonify, request
from ..extensions import db
from ..models import Experiment, RegisteredTarget
from ..services import (
    DockerService,
    DockerUnavailableError,
    SUPPORTED_FAULT_TYPES,
    DEFERRED_FAULT_TYPES,
    validate_experiment_parameters,
    ParameterValidationError,
    executor,
)

experiments_bp = Blueprint("experiments", __name__, url_prefix="/api/experiments")

# Five core fault categories defined in Master Specification Section 7
VALID_FAULT_TYPES = {
    "service_failure",
    "service_pause",
    "latency",
    "resource_stress",
    "http_error",
}


@experiments_bp.route("", methods=["POST"])
def create_experiment():
    """
    Create a validated experiment record in 'pending' status.
    Performs fresh live Docker validation to bind the experiment to an exact, active container ID.
    Validates parameter bounds (e.g., duration_seconds).
    """
    if not request.is_json:
        return jsonify({"error": "Bad Request", "message": "Request body must be JSON"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Bad Request", "message": "Invalid JSON payload"}), 400

    target_id = data.get("target_id")
    if target_id is None or not isinstance(target_id, int):
        return jsonify({"error": "Bad Request", "message": "'target_id' is required and must be an integer"}), 400

    fault_type = data.get("fault_type")
    if not fault_type or not isinstance(fault_type, str) or fault_type.strip().lower() not in VALID_FAULT_TYPES:
        return jsonify({
            "error": "Bad Request",
            "message": f"'fault_type' must be one of: {sorted(VALID_FAULT_TYPES)}"
        }), 400
    fault_type = fault_type.strip().lower()

    target_service = data.get("target_service")
    if not target_service or not isinstance(target_service, str) or not target_service.strip():
        return jsonify({"error": "Bad Request", "message": "'target_service' is required and must be a non-empty string"}), 400
    target_service = target_service.strip()

    raw_parameters = data.get("parameters", {})
    if raw_parameters is not None and not isinstance(raw_parameters, dict):
        return jsonify({"error": "Bad Request", "message": "'parameters' must be a dictionary"}), 400

    # Validate parameters if fault type is supported for execution
    try:
        validated_parameters = validate_experiment_parameters(fault_type, raw_parameters)
    except ParameterValidationError as e:
        return jsonify({"error": "Bad Request", "message": str(e)}), 400

    # 1. Verify Target existence and state
    target = db.session.get(RegisteredTarget, target_id)
    if not target:
        return jsonify({"error": "Not Found", "message": f"Target with id {target_id} does not exist."}), 404

    if target.status != "active":
        return jsonify({
            "error": "Bad Request",
            "message": f"Target '{target.name}' is currently {target.status}. Only active targets can accept experiments."
        }), 400

    if target.validation_status != "valid":
        return jsonify({
            "error": "Bad Request",
            "message": f"Target '{target.name}' must have validation_status 'valid' before creating experiments (currently: '{target.validation_status}'). Please run /api/targets/{target_id}/validate first."
        }), 400

    # 2. Check Target allowlist
    if target_service not in (target.allowed_services or []):
        return jsonify({
            "error": "Bad Request",
            "message": f"Service '{target_service}' is not in the target's authorized allowed_services list: {target.allowed_services}"
        }), 400

    # 3. Perform fresh live Docker validation (Never rely on cached discovery alone)
    docker_service = DockerService()
    try:
        is_valid, err_msg, container_info = docker_service.validate_service_for_experiment(
            compose_project=target.compose_project,
            service_name=target_service,
            allowed_services=target.allowed_services
        )
    except DockerUnavailableError as e:
        return jsonify({
            "error": "Docker Unavailable",
            "message": str(e)
        }), 503

    if not is_valid or not container_info:
        return jsonify({
            "error": "Target Service Validation Failed",
            "message": err_msg or "Failed to validate target service against live Docker daemon."
        }), 400

    # 4. Bind the pending experiment to the exact live container ID
    bound_container_id = container_info.get("container_id")

    experiment = Experiment(
        target_id=target.id,
        fault_type=fault_type,
        target_service=target_service,
        target_container_id=bound_container_id,
        parameters=validated_parameters,
        status="pending"
    )

    try:
        db.session.add(experiment)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "message": str(e)}), 500

    return jsonify(experiment.to_dict()), 201


@experiments_bp.route("/<int:experiment_id>/start", methods=["POST"])
def start_experiment(experiment_id: int):
    """
    Start execution of a pending experiment.
    Enforces revalidation of container identity, server parameter limits,
    concurrency locks, and graceful fault recovery.
    Runs asynchronously by default (returns HTTP 202), or synchronously if ?wait=true / ?sync=true.
    """
    # Check if synchronous execution was requested (useful for deterministic tests and scripts)
    wait_flag = request.args.get("wait", "").lower() in ("true", "1", "yes")
    sync_flag = request.args.get("sync", "").lower() in ("true", "1", "yes")
    is_sync = wait_flag or sync_flag

    app_instance = current_app._get_current_object()

    success, error_msg, exp_dict = executor.start_experiment(
        experiment_id=experiment_id,
        app=app_instance,
        background=(not is_sync),
    )

    if not success:
        if "not found" in (error_msg or "").lower():
            return jsonify({"error": "Not Found", "message": error_msg}), 404
        if "already running" in (error_msg or "").lower() or "active experiment running" in (error_msg or "").lower():
            return jsonify({"error": "Conflict", "message": error_msg}), 409
        if "docker daemon" in (error_msg or "").lower():
            return jsonify({"error": "Docker Unavailable", "message": error_msg}), 503
        return jsonify({"error": "Bad Request", "message": error_msg}), 400

    status_code = 200 if is_sync else 202
    return jsonify({
        "message": f"Experiment {experiment_id} started successfully.",
        "experiment": exp_dict
    }), status_code


@experiments_bp.route("", methods=["GET"])
def list_experiments():
    """List experiment records with optional query filtering."""
    query = Experiment.query

    target_id = request.args.get("target_id", type=int)
    if target_id is not None:
        query = query.filter_by(target_id=target_id)

    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status.strip().lower())

    fault_type = request.args.get("fault_type")
    if fault_type:
        query = query.filter_by(fault_type=fault_type.strip().lower())

    experiments = query.order_by(Experiment.created_at.desc()).all()
    return jsonify([exp.to_dict() for exp in experiments]), 200


@experiments_bp.route("/<int:experiment_id>", methods=["GET"])
def get_experiment(experiment_id: int):
    """Retrieve details for a specific experiment including metrics, observations, and recovery verification."""
    experiment = db.session.get(Experiment, experiment_id)
    if not experiment:
        return jsonify({"error": "Not Found", "message": f"Experiment with id {experiment_id} not found."}), 404
    return jsonify(experiment.to_dict()), 200


@experiments_bp.route("/<int:experiment_id>/cancel", methods=["POST"])
def cancel_experiment(experiment_id: int):
    """
    Cancel an experiment.
    - If status is 'pending': cancels immediately without touching target containers.
    - If status is 'running': signals cancellation to executor, triggering immediate cleanup and recovery.
    - If already finished/failed/cancelled: returns 400 Bad Request.
    """
    app_instance = current_app._get_current_object()
    success, message, status_code = executor.cancel_experiment(experiment_id, app=app_instance)

    experiment = db.session.get(Experiment, experiment_id)
    exp_data = experiment.to_dict() if experiment else None

    if not success:
        return jsonify({
            "error": "Bad Request" if status_code == 400 else "Error",
            "message": message,
            "experiment": exp_data
        }), status_code

    return jsonify({
        "message": message,
        "experiment": exp_data
    }), status_code
