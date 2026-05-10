import logging

from flask import Flask, jsonify

from app.config import config
from app.exceptions import BulkProcessingError


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1 MB upload limit

    _configure_logging()

    from app.routes.hospitals import bp as hospitals_bp
    app.register_blueprint(hospitals_bp)

    _register_error_handlers(app)

    return app


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if config.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(BulkProcessingError)
    def handle_bulk_error(exc: BulkProcessingError):
        return jsonify({"error": exc.message}), exc.status_code

    @app.errorhandler(413)
    def handle_too_large(_):
        return jsonify({"error": "File too large. Maximum upload size is 1 MB."}), 413

    @app.errorhandler(404)
    def handle_not_found(_):
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(_):
        return jsonify({"error": "Method not allowed"}), 405
