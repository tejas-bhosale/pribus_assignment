import io
import pytest
from app import create_app


@pytest.fixture
def app():
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def make_csv_file(content: str, filename: str = "hospitals.csv"):
    """Return a (data, filename, mimetype) tuple suitable for test_client file uploads."""
    return (io.BytesIO(content.encode()), filename, "text/csv")
