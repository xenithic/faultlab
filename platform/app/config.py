import os

class BaseConfig:
    """Base configuration shared across environments."""
    TESTING = False
    DEBUG = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Default local development credentials - strictly for isolated local environments
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "faultlab")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "faultlab_dev_password")
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "faultlab_platform")

    @classmethod
    def get_database_uri(cls) -> str:
        explicit_url = os.environ.get("DATABASE_URL")
        if explicit_url:
            return explicit_url
        return (
            f"postgresql+psycopg2://{cls.POSTGRES_USER}:{cls.POSTGRES_PASSWORD}"
            f"@{cls.POSTGRES_HOST}:{cls.POSTGRES_PORT}/{cls.POSTGRES_DB}"
        )


class DevelopmentConfig(BaseConfig):
    """Local development configuration with debug enabled."""
    DEBUG = True

    def __init__(self):
        self.SQLALCHEMY_DATABASE_URI = self.get_database_uri()


class TestingConfig(BaseConfig):
    """Testing configuration utilizing in-memory SQLite to decouple unit tests from live DB."""
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")


class ProductionConfig(BaseConfig):
    """Production configuration requiring explicit environment configuration."""
    DEBUG = False

    def __init__(self):
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            database_url = self.get_database_uri()
        self.SQLALCHEMY_DATABASE_URI = database_url


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(config_name: str | None = None):
    """Return the configuration class corresponding to the environment name."""
    name = (config_name or os.environ.get("FLASK_ENV", "development")).lower()
    config_cls = CONFIG_MAP.get(name, DevelopmentConfig)
    return config_cls()
