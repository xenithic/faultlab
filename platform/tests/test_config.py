import os
from app.config import get_config, DevelopmentConfig, TestingConfig, ProductionConfig


def test_development_config_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    cfg = get_config("development")
    assert isinstance(cfg, DevelopmentConfig)
    assert cfg.DEBUG is True
    assert cfg.TESTING is False
    assert cfg.SQLALCHEMY_DATABASE_URI.startswith("postgresql")
    assert "faultlab:faultlab_dev_password@localhost:5432/faultlab_platform" in cfg.SQLALCHEMY_DATABASE_URI


def test_custom_database_url_env(monkeypatch):
    custom_url = "postgresql://custom_user:custom_pass@db-host:5433/custom_db"
    monkeypatch.setenv("DATABASE_URL", custom_url)

    cfg = get_config("development")
    assert cfg.SQLALCHEMY_DATABASE_URI == custom_url


def test_testing_config():
    cfg = get_config("testing")
    assert isinstance(cfg, TestingConfig)
    assert cfg.TESTING is True
    assert cfg.DEBUG is True
    assert "sqlite:///:memory:" in cfg.SQLALCHEMY_DATABASE_URI


def test_production_config(monkeypatch):
    prod_url = "postgresql://prod_user:secret@prod-db:5432/faultlab_prod"
    monkeypatch.setenv("DATABASE_URL", prod_url)

    cfg = get_config("production")
    assert isinstance(cfg, ProductionConfig)
    assert cfg.DEBUG is False
    assert cfg.TESTING is False
    assert cfg.SQLALCHEMY_DATABASE_URI == prod_url
