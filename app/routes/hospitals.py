import logging

from flask import Blueprint, jsonify, request

from app.exceptions import BatchNotFoundError, BatchNotResumableError, CSVValidationError
from app.services import batch_service
from app.utils.csv_parser import parse_csv, validate_csv

logger = logging.getLogger(__name__)

bp = Blueprint("hospitals", __name__, url_prefix="/hospitals")


@bp.route("/bulk", methods=["POST"])
def bulk_create():
    """
    Accept a CSV file and synchronously create + activate all hospitals.

    Form fields:
        file (required): CSV with columns name, address, phone (phone optional)

    Returns 200 with full processing results on success/partial failure.
    Returns 400 if the CSV is invalid.
    """
    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' field in multipart form data"}), 400

    file = request.files["file"]

    try:
        hospitals = parse_csv(file)
    except CSVValidationError as exc:
        return jsonify({"error": exc.message}), 400

    batch = batch_service.process_bulk(hospitals)
    return jsonify(batch.to_dict()), 200


@bp.route("/bulk/<batch_id>/status", methods=["GET"])
def batch_status(batch_id: str):
    """Return the current or final status of a previously submitted batch."""
    try:
        batch = batch_service.get_batch(batch_id)
    except BatchNotFoundError as exc:
        return jsonify({"error": exc.message}), 404
    return jsonify(batch.to_dict()), 200


@bp.route("/bulk/<batch_id>/resume", methods=["POST"])
def resume_batch(batch_id: str):
    """
    Retry all failed hospitals in a batch and re-attempt activation.

    Only valid for batches in 'failed' or 'partially_failed' status.
    """
    try:
        batch = batch_service.resume_batch(batch_id)
    except BatchNotFoundError as exc:
        return jsonify({"error": exc.message}), 404
    except BatchNotResumableError as exc:
        return jsonify({"error": exc.message}), 409
    return jsonify(batch.to_dict()), 200


@bp.route("/validate", methods=["POST"])
def validate():
    """
    Validate a CSV file without creating any hospitals.

    Returns a report indicating which rows (if any) have errors,
    along with warnings for unknown columns.
    """
    if "file" not in request.files:
        return jsonify({"error": "Missing 'file' field in multipart form data"}), 400

    file = request.files["file"]

    try:
        report = validate_csv(file)
    except CSVValidationError as exc:
        return jsonify({"error": exc.message}), 400

    status_code = 200 if report["valid"] else 422
    return jsonify(report), status_code
