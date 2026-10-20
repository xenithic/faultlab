from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError
from ..extensions import db
from ..models import RegisteredTarget
from ..services import DockerService, DockerUnavailableError

targets_bp = Blueprint("targets", __name__, url_prefix="/api/targets")


@targets_bp.route("", methods=["POST"])
def register_target():
    """
    Register an isolated target environment for resilience testing.
    Requires an explicit non-empty allowlist of services.
    """
    if not request.is_json:
        return jsonify({"error": "Bad Request", "message": "Request body must be JSON"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Bad Request", "message": "Invalid JSON payload"}), 400

    name = data.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        return jsonify({"error": "Bad Request", "message": "'name' is required and must be a non-empty string"}), 400
    name = name.strip()

    compose_project = data.get("compose_project")
    if not compose_project or not isinstance(compose_project, str) or not compose_project.strip():
        return jsonify({"error": "Bad Request", "message": "'compose_project' is required and must be a non-empty string"}), 400
    compose_project = compose_project.strip()

    description = data.get("description", "")
    target_type = data.get("target_type", "docker_compose")

    # Explicit allowlist of authorized services
    allowed_services = data.get("allowed_services")
    if allowed_services is None or not isinstance(allowed_services, list) or len(allowed_services) == 0:
        return jsonify({
            "error": "Bad Request",
            "message": "'allowed_services' is required and must be a non-empty list of service names."
        }), 400

    # Ensure all items in allowed_services are non-empty strings
    cleaned_allowed = []
    for s in allowed_services:
        if not isinstance(s, str) or not s.strip():
            return jsonify({
                "error": "Bad Request",
                "message": "All items in 'allowed_services' must be non-empty strings."
            }), 400
        cleaned_allowed.append(s.strip())

    # Check that protected infrastructure is not in allowlist
    from ..services.docker_service import PROTECTED_SERVICES
    disallowed_found = [s for s in cleaned_allowed if s.lower() in PROTECTED_SERVICES]
    if disallowed_found:
        return jsonify({
            "error": "Bad Request",
            "message": f"Protected platform components cannot be registered as targets: {disallowed_found}"
        }), 400

    target = RegisteredTarget(
        name=name,
        description=description,
        target_type=target_type,
        compose_project=compose_project,
        allowed_services=cleaned_allowed,
        validation_status="unvalidated",
        status="active"
    )

    try:
        db.session.add(target)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({
            "error": "Conflict",
            "message": f"A target with name '{name}' already exists."
        }), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "error": "Database Error",
            "message": f"Failed to persist registered target: {str(e)}"
        }), 500

    return jsonify(target.to_dict()), 201


@targets_bp.route("", methods=["GET"])
def list_targets():
    """List all registered targets."""
    targets = RegisteredTarget.query.order_by(RegisteredTarget.created_at.asc()).all()
    return jsonify([t.to_dict() for t in targets]), 200


@targets_bp.route("/<int:target_id>", methods=["GET"])
def get_target(target_id: int):
    """Retrieve details and discovery metadata for a specific target."""
    target = db.session.get(RegisteredTarget, target_id)
    if not target:
        return jsonify({"error": "Not Found", "message": f"Target with id {target_id} not found."}), 404
    return jsonify(target.to_dict()), 200


@targets_bp.route("/<int:target_id>/validate", methods=["POST"])
def validate_target(target_id: int):
    """
    Perform on-demand live Docker inspection of the target environment.
    Updates discovered services and validation status.
    """
    target = db.session.get(RegisteredTarget, target_id)
    if not target:
        return jsonify({"error": "Not Found", "message": f"Target with id {target_id} not found."}), 404

    docker_service = DockerService()
    try:
        validation_result = docker_service.discover_and_validate_target(
            compose_project=target.compose_project,
            allowed_services=target.allowed_services
        )
    except DockerUnavailableError as e:
        target.validation_status = "unreachable"
        db.session.commit()
        return jsonify({
            "error": "Docker Unavailable",
            "message": str(e),
            "target": target.to_dict()
        }), 503

    target.validation_status = validation_result["validation_status"]
    target.last_validated_at = datetime.now(timezone.utc)
    target.discovered_services = validation_result["discovered_services"]

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "message": str(e)}), 500

    return jsonify({
        "target": target.to_dict(),
        "validation_report": validation_result
    }), 200


@targets_bp.route("/<int:target_id>", methods=["DELETE"])
def delete_target(target_id: int):
    """Unregister / remove a target environment and its experiments."""
    target = db.session.get(RegisteredTarget, target_id)
    if not target:
        return jsonify({"error": "Not Found", "message": f"Target with id {target_id} not found."}), 404

    target_name = target.name
    try:
        db.session.delete(target)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database Error", "message": str(e)}), 500

    return jsonify({
        "message": f"Target '{target_name}' (id: {target_id}) and its associated experiments were deleted successfully."
    }), 200
