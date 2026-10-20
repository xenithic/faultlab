from flask import Blueprint, jsonify
from sqlalchemy import text
from ..extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/", methods=["GET"])
def index():
    """Platform root information endpoint."""
    return jsonify({
        "service": "faultlab-platform",
        "description": "FaultLab Chaos Engineering & Resilience Testing Platform",
        "version": "0.1.0"
    }), 200


@health_bp.route("/health", methods=["GET"])
def health():
    """Basic platform liveness healthcheck endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "faultlab-platform",
        "version": "0.1.0"
    }), 200


@health_bp.route("/health/db", methods=["GET"])
def health_db():
    """Database connectivity healthcheck endpoint."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({
            "status": "healthy",
            "service": "faultlab-platform",
            "database": "connected"
        }), 200
    except Exception as e:
        return jsonify({
            "status": "degraded",
            "service": "faultlab-platform",
            "database": "disconnected",
            "error": str(e)
        }), 503
