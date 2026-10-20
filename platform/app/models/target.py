import datetime
from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from ..extensions import db


class RegisteredTarget(db.Model):
    """
    Represents an isolated target environment registered for resilience testing.
    Kept generic and independent of specific service names or target topology.
    Requires an explicit list of allowed services and dynamic Docker metadata validation.
    """
    __tablename__ = "registered_targets"

    id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(String(128), unique=True, nullable=False, index=True)
    description = db.Column(Text, nullable=True)
    target_type = db.Column(String(64), nullable=False, default="docker_compose")
    compose_project = db.Column(String(256), nullable=False)
    status = db.Column(String(32), nullable=False, default="active")

    # Explicit allowlist of authorized service names within this target environment
    # An empty or omitted list must not authorize services
    allowed_services = db.Column(JSON, nullable=False, default=list)

    # Validation state: 'unvalidated', 'valid', 'invalid', 'unreachable'
    validation_status = db.Column(String(32), nullable=False, default="unvalidated")
    last_validated_at = db.Column(DateTime(timezone=True), nullable=True)

    # Cached discovery metadata from the most recent validation
    discovered_services = db.Column(JSON, nullable=True)

    created_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
    )

    experiments = relationship(
        "Experiment",
        back_populates="target",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target_type": self.target_type,
            "compose_project": self.compose_project,
            "status": self.status,
            "allowed_services": self.allowed_services or [],
            "validation_status": self.validation_status,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "discovered_services": self.discovered_services,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<RegisteredTarget id={self.id} name={self.name!r} "
            f"compose_project={self.compose_project!r} validation_status={self.validation_status!r}>"
        )
