import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from ..extensions import db


class Experiment(db.Model):
    """
    Represents an experiment execution record against a registered target.
    Stores lifecycle status, parameters, timing, bound container ID, and metric outcomes.
    """
    __tablename__ = "experiments"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    target_id = db.Column(
        Integer,
        ForeignKey("registered_targets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fault_type = db.Column(String(64), nullable=False, index=True)
    target_service = db.Column(String(128), nullable=False)
    # The exact validated Docker container ID bound at experiment creation
    target_container_id = db.Column(String(64), nullable=True)

    parameters = db.Column(JSON, nullable=True)
    # Status lifecycle: 'pending', 'cancelled', 'running', 'completed', 'failed'
    status = db.Column(String(32), nullable=False, default="pending", index=True)

    started_at = db.Column(DateTime(timezone=True), nullable=True)
    ended_at = db.Column(DateTime(timezone=True), nullable=True)
    recovery_time_seconds = db.Column(Float, nullable=True)

    baseline_metrics = db.Column(JSON, nullable=True)
    result_metrics = db.Column(JSON, nullable=True)

    # Error message if validation or execution fails
    error_message = db.Column(Text, nullable=True)

    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    target = relationship("RegisteredTarget", back_populates="experiments")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target_id": self.target_id,
            "fault_type": self.fault_type,
            "target_service": self.target_service,
            "target_container_id": self.target_container_id,
            "parameters": self.parameters or {},
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "recovery_time_seconds": self.recovery_time_seconds,
            "baseline_metrics": self.baseline_metrics or {},
            "result_metrics": self.result_metrics or {},
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Experiment id={self.id} target_id={self.target_id} "
            f"service={self.target_service!r} fault_type={self.fault_type!r} status={self.status!r}>"
        )
