import os
import pytest
from sqlalchemy import text
from app import create_app, db
from app.models import RegisteredTarget, Experiment


@pytest.mark.skipif(
    not os.environ.get("TEST_LIVE_DB"),
    reason="TEST_LIVE_DB environment variable not set; skipping live PostgreSQL integration tests."
)
def test_live_postgres_connectivity_and_crud():
    """
    Validates end-to-end integration against real PostgreSQL when configured.
    Run with TEST_LIVE_DB=1 to execute.
    """
    app = create_app("development")
    with app.app_context():
        # Verify raw SQL connectivity
        result = db.session.execute(text("SELECT current_database(), current_user;")).fetchone()
        assert result is not None
        assert result[0] == "faultlab_platform"

        # Verify model persistence in PostgreSQL
        target = RegisteredTarget(
            name="integration-pg-target",
            description="Verified against live PostgreSQL",
            compose_project="target-app",
            allowed_services=["product-service"]
        )
        db.session.add(target)
        db.session.commit()

        exp = Experiment(
            target_id=target.id,
            fault_type="latency",
            target_service="product-service",
            target_container_id="c_live_pg_123",
            parameters={"delay_ms": 350},
            status="pending"
        )
        db.session.add(exp)
        db.session.commit()

        # Query back and verify
        fetched_target = RegisteredTarget.query.filter_by(name="integration-pg-target").first()
        assert fetched_target is not None
        assert fetched_target.experiments.count() == 1
        assert fetched_target.experiments.first().parameters["delay_ms"] == 350

        # Cleanup test data
        db.session.delete(fetched_target)
        db.session.commit()
