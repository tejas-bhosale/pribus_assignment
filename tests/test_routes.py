import io
import json
import pytest
from unittest.mock import patch, MagicMock

from app.models.batch import BatchRecord, BatchStatus, HospitalInput, HospitalRecord, HospitalRecordStatus
from tests.conftest import make_csv_file


VALID_CSV = "name,address,phone\nGeneral Hospital,123 Main St,555-1234\nCity Clinic,456 Oak Ave,"


def _completed_batch(batch_id="test-batch-id"):
    inputs = [
        HospitalInput("General Hospital", "123 Main St", "555-1234"),
        HospitalInput("City Clinic", "456 Oak Ave"),
    ]
    records = [
        HospitalRecord(row=1, name="General Hospital", status=HospitalRecordStatus.CREATED_AND_ACTIVATED, hospital_id=101),
        HospitalRecord(row=2, name="City Clinic", status=HospitalRecordStatus.CREATED_AND_ACTIVATED, hospital_id=102),
    ]
    batch = BatchRecord(
        batch_id=batch_id,
        hospital_inputs=inputs,
        hospitals=records,
        total_hospitals=2,
        status=BatchStatus.COMPLETED,
        processed_hospitals=2,
        failed_hospitals=0,
        batch_activated=True,
        completed_at=1000.0,
        started_at=990.0,
    )
    return batch


class TestBulkCreate:
    def test_returns_200_on_success(self, client):
        batch = _completed_batch()

        with patch("app.routes.hospitals.batch_service.process_bulk", return_value=batch):
            resp = client.post(
                "/hospitals/bulk",
                data={"file": make_csv_file(VALID_CSV)},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["batch_id"] == "test-batch-id"
        assert data["total_hospitals"] == 2
        assert data["batch_activated"] is True

    def test_missing_file_returns_400(self, client):
        resp = client.post("/hospitals/bulk", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert "file" in resp.get_json()["error"].lower()

    def test_invalid_csv_missing_column_returns_400(self, client):
        bad_csv = make_csv_file("address\n123 Main St")
        resp = client.post(
            "/hospitals/bulk",
            data={"file": bad_csv},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "name" in resp.get_json()["error"].lower()

    def test_csv_exceeding_limit_returns_400(self, client):
        rows = "\n".join(f"Hospital {i},Address {i}" for i in range(21))
        big_csv = make_csv_file(f"name,address\n{rows}")
        resp = client.post(
            "/hospitals/bulk",
            data={"file": big_csv},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_response_shape_matches_spec(self, client):
        batch = _completed_batch()

        with patch("app.routes.hospitals.batch_service.process_bulk", return_value=batch):
            resp = client.post(
                "/hospitals/bulk",
                data={"file": make_csv_file(VALID_CSV)},
                content_type="multipart/form-data",
            )

        data = resp.get_json()
        required_keys = {
            "batch_id", "total_hospitals", "processed_hospitals",
            "failed_hospitals", "processing_time_seconds", "batch_activated", "hospitals",
        }
        assert required_keys.issubset(data.keys())
        assert isinstance(data["hospitals"], list)
        assert data["hospitals"][0]["row"] == 1
        assert data["hospitals"][0]["status"] == "created_and_activated"


class TestBatchStatus:
    def test_returns_batch_for_known_id(self, client):
        batch = _completed_batch("abc-123")

        with patch("app.routes.hospitals.batch_service.get_batch", return_value=batch):
            resp = client.get("/hospitals/bulk/abc-123/status")

        assert resp.status_code == 200
        assert resp.get_json()["batch_id"] == "abc-123"

    def test_unknown_id_returns_404(self, client):
        from app.exceptions import BatchNotFoundError

        with patch(
            "app.routes.hospitals.batch_service.get_batch",
            side_effect=BatchNotFoundError("missing-id"),
        ):
            resp = client.get("/hospitals/bulk/missing-id/status")

        assert resp.status_code == 404


class TestResumeBatch:
    def test_resume_returns_updated_batch(self, client):
        batch = _completed_batch("resume-id")
        batch.status = BatchStatus.COMPLETED  # will be returned after resume

        with patch("app.routes.hospitals.batch_service.resume_batch", return_value=batch):
            resp = client.post("/hospitals/bulk/resume-id/resume")

        assert resp.status_code == 200
        assert resp.get_json()["batch_id"] == "resume-id"

    def test_non_resumable_batch_returns_409(self, client):
        from app.exceptions import BatchNotResumableError

        with patch(
            "app.routes.hospitals.batch_service.resume_batch",
            side_effect=BatchNotResumableError("done-id", "completed"),
        ):
            resp = client.post("/hospitals/bulk/done-id/resume")

        assert resp.status_code == 409


class TestValidate:
    def test_valid_csv_returns_200(self, client):
        resp = client.post(
            "/hospitals/validate",
            data={"file": make_csv_file(VALID_CSV)},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert resp.get_json()["valid"] is True

    def test_invalid_csv_returns_422(self, client):
        bad = make_csv_file("name,address\n,No Name Hospital")
        resp = client.post(
            "/hospitals/validate",
            data={"file": bad},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 422
        data = resp.get_json()
        assert data["valid"] is False
        assert data["errors"]

    def test_missing_file_returns_400(self, client):
        resp = client.post("/hospitals/validate", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
