import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from app import create_app, db
from app.models import RegisteredTarget, Experiment


@pytest.fixture
def app_ctx():
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.rollback()
        db.drop_all()


def test_create_registered_target(app_ctx):
    target = RegisteredTarget(
        name="local-demo-cluster",
        description="Controlled local test target environment",
        target_type="docker_compose",
        compose_project="target-app",
        allowed_services=["product-service", "order-service"],
        status="active"
    )
    db.session.add(target)
    db.session.commit()

    saved = RegisteredTarget.query.filter_by(name="local-demo-cluster").first()
    assert saved is not None
    assert saved.id is not None
    assert saved.compose_project == "target-app"
    assert saved.status == "active"
    assert saved.allowed_services == ["product-service", "order-service"]
    assert saved.validation_status == "unvalidated"
    assert isinstance(saved.created_at, datetime)

    data = saved.to_dict()
    assert data["name"] == "local-demo-cluster"
    assert data["target_type"] == "docker_compose"
    assert data["validation_status"] == "unvalidated"


def test_target_unique_name_constraint(app_ctx):
    t1 = RegisteredTarget(name="unique-target", compose_project="proj-1", allowed_services=["svc-1"])
    t2 = RegisteredTarget(name="unique-target", compose_project="proj-2", allowed_services=["svc-2"])
    db.session.add(t1)
    db.session.commit()

    db.session.add(t2)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_create_experiment_and_relationship(app_ctx):
    target = RegisteredTarget(
        name="resilience-target",
        compose_project="resilience-proj",
        allowed_services=["order-service"]
    )
    db.session.add(target)
    db.session.commit()

    experiment = Experiment(
        target_id=target.id,
        fault_type="service_failure",
        target_service="order-service",
        target_container_id="c1234567890abcdef",
        parameters={"duration_seconds": 15, "signal": "SIGKILL"},
        status="pending",
        baseline_metrics={"p95_latency_ms": 32.5, "error_rate": 0.0},
    )
    db.session.add(experiment)
    db.session.commit()

    saved_exp = Experiment.query.filter_by(id=experiment.id).first()
    assert saved_exp is not None
    assert saved_exp.target.name == "resilience-target"
    assert saved_exp.target_service == "order-service"
    assert saved_exp.target_container_id == "c1234567890abcdef"
    assert saved_exp.parameters["duration_seconds"] == 15
    assert saved_exp.baseline_metrics["p95_latency_ms"] == 32.5
    assert target.experiments.count() == 1

    # Test serialization
    exp_dict = saved_exp.to_dict()
    assert exp_dict["status"] == "pending"
    assert exp_dict["fault_type"] == "service_failure"
    assert exp_dict["target_container_id"] == "c1234567890abcdef"


def test_target_experiment_cascade_delete(app_ctx):
    target = RegisteredTarget(
        name="temp-target",
        compose_project="temp-proj",
        allowed_services=["order-service", "payment-service"]
    )
    db.session.add(target)
    db.session.commit()

    exp1 = Experiment(target_id=target.id, fault_type="latency", target_service="order-service", status="pending")
    exp2 = Experiment(target_id=target.id, fault_type="http_error", target_service="payment-service", status="cancelled")
    db.session.add_all([exp1, exp2])
    db.session.commit()

    assert Experiment.query.filter_by(target_id=target.id).count() == 2

    db.session.delete(target)
    db.session.commit()

    assert Experiment.query.filter_by(target_id=target.id).count() == 0
