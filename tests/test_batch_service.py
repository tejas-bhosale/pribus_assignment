import pytest
from unittest.mock import patch, MagicMock

from app.exceptions import BatchNotFoundError, BatchNotResumableError, ExternalAPIError
from app.models.batch import BatchStatus, HospitalInput, HospitalRecordStatus
from app.services import batch_service


def _make_inputs(n: int = 2) -> list:
    return [HospitalInput(name=f"Hospital {i}", address=f"Addr {i}") for i in range(n)]


def _hospital_response(idx: int) -> dict:
    return {"id": 100 + idx, "name": f"Hospital {idx}", "active": False}


class TestProcessBulk:
    def test_all_succeed_activates_batch(self):
        inputs = _make_inputs(3)

        def fake_create(hospital, batch_id):
            i = int(hospital.name.split()[-1])
            return _hospital_response(i)

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.side_effect = fake_create
            mock_client.activate_batch.return_value = {"activated": True}

            batch = batch_service.process_bulk(inputs)

        assert batch.status == BatchStatus.COMPLETED
        assert batch.batch_activated is True
        assert batch.failed_hospitals == 0
        assert batch.processed_hospitals == 3
        assert all(
            r.status == HospitalRecordStatus.CREATED_AND_ACTIVATED
            for r in batch.hospitals
        )
        mock_client.activate_batch.assert_called_once_with(batch.batch_id)

    def test_partial_failure_skips_activation(self):
        inputs = _make_inputs(3)

        def fake_create(hospital, batch_id):
            if hospital.name == "Hospital 1":
                raise ExternalAPIError("timeout")
            i = int(hospital.name.split()[-1])
            return _hospital_response(i)

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.side_effect = fake_create

            batch = batch_service.process_bulk(inputs)

        assert batch.status == BatchStatus.PARTIALLY_FAILED
        assert batch.batch_activated is False
        assert batch.failed_hospitals == 1
        mock_client.activate_batch.assert_not_called()

    def test_all_fail_returns_failed_status(self):
        inputs = _make_inputs(2)

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.side_effect = ExternalAPIError("server error")

            batch = batch_service.process_bulk(inputs)

        assert batch.status == BatchStatus.FAILED
        assert batch.batch_activated is False
        assert batch.processed_hospitals == 2
        assert batch.failed_hospitals == 2

    def test_activation_failure_recorded(self):
        inputs = _make_inputs(2)

        def fake_create(hospital, batch_id):
            i = int(hospital.name.split()[-1])
            return _hospital_response(i)

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.side_effect = fake_create
            mock_client.activate_batch.side_effect = ExternalAPIError("activate failed")

            batch = batch_service.process_bulk(inputs)

        assert batch.batch_activated is False
        assert batch.error is not None

    def test_hospital_ids_stored_on_records(self):
        inputs = [HospitalInput(name="Memorial", address="1 Park Ave", phone="555-0001")]

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.return_value = {"id": 42, "name": "Memorial"}
            mock_client.activate_batch.return_value = {}

            batch = batch_service.process_bulk(inputs)

        assert batch.hospitals[0].hospital_id == 42

    def test_batch_stored_in_memory(self):
        inputs = _make_inputs(1)

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.return_value = {"id": 1}
            mock_client.activate_batch.return_value = {}

            batch = batch_service.process_bulk(inputs)

        retrieved = batch_service.get_batch(batch.batch_id)
        assert retrieved.batch_id == batch.batch_id


class TestGetBatch:
    def test_unknown_id_raises(self):
        with pytest.raises(BatchNotFoundError):
            batch_service.get_batch("00000000-0000-0000-0000-000000000000")


class TestResumeBatch:
    def test_resume_retries_failed_records(self):
        inputs = _make_inputs(2)

        call_count = {"n": 0}

        def flaky_create(hospital, batch_id):
            # Fail on first call for Hospital 1, succeed on retry
            if hospital.name == "Hospital 1" and call_count["n"] == 0:
                call_count["n"] += 1
                raise ExternalAPIError("timeout")
            return {"id": int(hospital.name.split()[-1]) + 100}

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.side_effect = flaky_create

            # First pass: one failure, no activation
            batch = batch_service.process_bulk(inputs)

        assert batch.status == BatchStatus.PARTIALLY_FAILED

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.return_value = {"id": 999}
            mock_client.activate_batch.return_value = {}

            resumed = batch_service.resume_batch(batch.batch_id)

        assert resumed.status == BatchStatus.COMPLETED
        assert resumed.batch_activated is True

    def test_resume_completed_batch_raises(self):
        inputs = _make_inputs(1)

        with patch("app.services.batch_service.hospital_client") as mock_client:
            mock_client.create_hospital.return_value = {"id": 1}
            mock_client.activate_batch.return_value = {}

            batch = batch_service.process_bulk(inputs)

        assert batch.status == BatchStatus.COMPLETED

        with pytest.raises(BatchNotResumableError):
            batch_service.resume_batch(batch.batch_id)
