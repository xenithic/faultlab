import os
from dotenv import load_dotenv

# Load local environment configuration if available
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

from app import create_app, db
from app.models import RegisteredTarget, Experiment

# Instantiate application using environment config
env_name = os.environ.get("FLASK_ENV", "development")
app = create_app(env_name)


@app.shell_context_processor
def make_shell_context():
    """Provides CLI access to DB and core models in 'flask shell'."""
    return {
        "db": db,
        "RegisteredTarget": RegisteredTarget,
        "Experiment": Experiment,
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = app.config.get("DEBUG", False)
    app.run(host="0.0.0.0", port=port, debug=debug)
