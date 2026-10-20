from flask import Flask, jsonify
from .config import get_config
from .extensions import db, migrate


def create_app(config_name: str | None = None) -> Flask:
    """
    Application factory for the FaultLab Platform backend.
    """
    app = Flask(__name__)
    config_obj = get_config(config_name)
    app.config.from_object(config_obj)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Ensure models are registered with SQLAlchemy metadata
    from . import models  # noqa: F401

    # Register blueprints
    from .routes import health_bp, targets_bp, experiments_bp
    app.register_blueprint(health_bp)
    app.register_blueprint(targets_bp)
    app.register_blueprint(experiments_bp)

    # Register standard JSON error handlers
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            "error": "Bad Request",
            "message": str(error)
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": "Not Found",
            "message": "The requested resource was not found on FaultLab platform."
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            "error": "Method Not Allowed",
            "message": "The method is not allowed for the requested URL."
        }), 405

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            "error": "Internal Server Error",
            "message": "An unexpected error occurred on the FaultLab platform backend."
        }), 500

    return app
