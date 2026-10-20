from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Experiment, RegisteredTarget
from ..services import DockerService, DockerUnavailableError

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
    Strictly does NOT trigger fault injection or collect metrics in Milestone 2.
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

    parameters = data.get("parameters", {})
    if parameters is not None and not isinstance(parameters, dict):
        return jsonify({"error": "Bad Request", "message": "'parameters' must be a dictionary"}), 400

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
        parameters=parameters,
        status="pending"
    )

    try:
        db.session.add(experiment)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "message": str(e)}), 500

    return jsonify(experiment.to_dict()), 201


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

    experiments = query.order_by(Experiment.created_at.desc()).all()
    return jsonify([exp.to_dict() for exp in experiments]), 200


@experiments_bp.route("/<int:experiment_id>", methods=["GET"])
def get_experiment(experiment_id: int):
    """Retrieve details for a specific experiment."""
    experiment = db.session.get(Experiment, experiment_id)
    if not experiment:
        return jsonify({"error": "Not Found", "message": f"Experiment with id {experiment_id} not found."}), 404
    return jsonify(experiment.to_dict()), 200


@experiments_bp.route("/<int:experiment_id>/cancel", methods=["POST"])
def cancel_experiment(experiment_id: int):
    """Cancel a pending experiment."""
    experiment = db.session.get(Experiment, experiment_id)
    if not experiment:
        return jsonify({"error": "Not Found", "message": f"Experiment with id {experiment_id} not found."}), 404

    if experiment.status != "pending":
        return jsonify({
            "error": "Bad Request",
            "message": f"Cannot cancel experiment with status '{experiment.status}'. Only 'pending' experiments can be cancelled."
        }), 400

    experiment.status = "cancelled"
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "message": str(e)}), 500

    return jsonify({
        "message": f"Experiment {experiment_id} was successfully cancelled.",
        "experiment": experiment.to_dict()
    }), 200
