"""
FaultLab Application-Layer Fault Interceptor Middleware for Target Services.
Provides safe, controlled, bounded network latency and HTTP error injection.
"""
import logging
import os
import random
import threading
import time
from typing import Any
from flask import Blueprint, Flask, jsonify, request

logger = logging.getLogger("faultlab.interceptor")

FAULTLAB_CONTROL_SECRET = os.environ.get(
    "FAULTLAB_CONTROL_SECRET", "faultlab-internal-control-secret"
)

VALID_HTTP_ERROR_CODES = {400, 404, 429, 500, 502, 503, 504}


class FaultState:
    """Thread-safe state container for active application-layer faults."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = False
        self.fault_type = None  # "latency" or "http_error"
        self.latency_ms = 0
        self.jitter_ms = 0
        self.error_code = 500
        self.error_rate = 1.0
        self.error_message = "FaultLab Injected Fault"
        self.duration_seconds = 10.0
        self.started_at = 0.0
        self.expires_at = 0.0
        self.target_routes: list[str] | None = None

    def inject_fault(self, config: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            fault_type = str(config.get("fault_type", "latency")).strip().lower()
            if fault_type not in ("latency", "http_error"):
                raise ValueError(f"Invalid fault_type '{fault_type}'. Expected 'latency' or 'http_error'.")

            duration = float(config.get("duration_seconds", 10))
            if duration < 1.0 or duration > 300.0:
                raise ValueError("duration_seconds must be between 1 and 300.")

            self.fault_type = fault_type
            self.duration_seconds = duration

            if fault_type == "latency":
                latency = int(config.get("latency_ms", config.get("delay_ms", 500)))
                if latency < 10 or latency > 10000:
                    raise ValueError("latency_ms must be between 10 and 10000.")
                self.latency_ms = latency
                self.jitter_ms = max(0, min(int(config.get("jitter_ms", 0)), latency))

            elif fault_type == "http_error":
                code = int(config.get("error_code", 500))
                if code not in VALID_HTTP_ERROR_CODES:
                    raise ValueError(f"error_code must be one of {sorted(VALID_HTTP_ERROR_CODES)}")
                self.error_code = code

                rate = float(config.get("error_rate", 1.0))
                if rate > 1.0 and rate <= 100.0:
                    rate = rate / 100.0
                if rate < 0.01 or rate > 1.0:
                    raise ValueError("error_rate must be between 0.01 and 1.0.")
                self.error_rate = rate
                self.error_message = str(
                    config.get("error_message", f"FaultLab Injected HTTP {code} Failure")
                )[:200]

            routes = config.get("target_routes")
            self.target_routes = [str(r) for r in routes] if isinstance(routes, list) else None

            self.started_at = time.time()
            self.expires_at = self.started_at + self.duration_seconds
            self.active = True

            logger.info(
                "Fault injected on target service: type=%s, duration=%.1fs, expires_at=%.2f",
                self.fault_type, self.duration_seconds, self.expires_at
            )
            return self._build_status_dict(locked=True)

    def clear_fault(self) -> dict[str, Any]:
        with self._lock:
            was_active = self.active
            self.active = False
            self.fault_type = None
            self.latency_ms = 0
            self.jitter_ms = 0
            self.error_code = 500
            self.error_rate = 1.0
            self.expires_at = 0.0
            self.target_routes = None
            logger.info("Fault cleared. was_active=%s", was_active)
            return {"active": False, "status": "recovered", "was_active": was_active}

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return self._build_status_dict(locked=True)

    def _build_status_dict(self, locked: bool = True) -> dict[str, Any]:
        now = time.time()
        if self.active and now >= self.expires_at:
            # Auto-expire after duration window
            self.active = False
            self.fault_type = None

        time_remaining = max(0.0, round(self.expires_at - now, 2)) if self.active else 0.0
        return {
            "active": self.active,
            "fault_type": self.fault_type,
            "duration_seconds": self.duration_seconds if self.active else None,
            "latency_ms": self.latency_ms if (self.active and self.fault_type == "latency") else None,
            "jitter_ms": self.jitter_ms if (self.active and self.fault_type == "latency") else None,
            "error_code": self.error_code if (self.active and self.fault_type == "http_error") else None,
            "error_rate": self.error_rate if (self.active and self.fault_type == "http_error") else None,
            "error_message": self.error_message if (self.active and self.fault_type == "http_error") else None,
            "time_remaining_seconds": time_remaining,
        }

    def maybe_intercept(self, path: str):
        with self._lock:
            if not self.active:
                return None
            now = time.time()
            if now >= self.expires_at:
                self.active = False
                self.fault_type = None
                return None

            fault_type = self.fault_type
            latency_ms = self.latency_ms
            jitter_ms = self.jitter_ms
            error_code = self.error_code
            error_rate = self.error_rate
            error_msg = self.error_message
            target_routes = self.target_routes

        # Check route filter
        if target_routes:
            if not any(path.startswith(r) for r in target_routes):
                return None

        if fault_type == "latency":
            delay_sec = latency_ms / 1000.0
            if jitter_ms > 0:
                jitter_sec = random.uniform(-jitter_ms, jitter_ms) / 1000.0
                delay_sec = max(0.001, delay_sec + jitter_sec)
            if delay_sec > 0:
                time.sleep(delay_sec)
            return None

        elif fault_type == "http_error":
            if error_rate >= 1.0 or random.random() < error_rate:
                return jsonify({
                    "error": error_msg,
                    "fault_type": "http_error",
                    "status_code": error_code,
                    "path": path,
                }), error_code

        return None


def init_fault_interceptor(app: Flask) -> FaultState:
    """Initialize and attach fault interceptor blueprint and hook to Flask app."""
    state = FaultState()
    bp = Blueprint("faultlab_interceptor", __name__, url_prefix="/_faultlab")

    def _is_authorized() -> bool:
        auth_header = request.headers.get("X-FaultLab-Secret")
        if auth_header and auth_header == FAULTLAB_CONTROL_SECRET:
            return True
        if request.is_json:
            data = request.get_json(silent=True) or {}
            if data.get("secret") == FAULTLAB_CONTROL_SECRET:
                return True
        remote = request.remote_addr or ""
        if remote in ("127.0.0.1", "localhost", "::1"):
            return True
        return False

    @bp.route("/fault", methods=["POST"])
    def inject():
        if not _is_authorized():
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        if data.get("active") is False:
            return jsonify(state.clear_fault()), 200

        try:
            res = state.inject_fault(data)
            return jsonify(res), 200
        except ValueError as e:
            return jsonify({"error": "Bad Request", "message": str(e)}), 400

    @bp.route("/fault", methods=["DELETE"])
    def clear():
        if not _is_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify(state.clear_fault()), 200

    @bp.route("/fault", methods=["GET"])
    def status():
        if not _is_authorized():
            return jsonify({"error": "Unauthorized"}), 401
        return jsonify(state.get_status()), 200

    app.register_blueprint(bp)

    @app.before_request
    def intercept_traffic():
        # Never intercept internal control endpoints or Docker liveness healthcheck
        if request.path.startswith("/_faultlab") or request.path == "/health":
            return None
        return state.maybe_intercept(request.path)

    app.extensions = getattr(app, "extensions", {})
    app.extensions["faultlab_state"] = state
    return state
