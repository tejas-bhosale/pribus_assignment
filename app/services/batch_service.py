"""Core business logic for bulk hospital processing.

Design notes:
- Processing is synchronous from the caller's perspective: POST /hospitals/bulk blocks
  until all hospitals are created and the batch is activated (or fails).
- Hospital creation requests are fired concurrently via ThreadPoolExecutor to keep
  wall-clock time close to a single API call rather than N * RTT.
- Every processed batch is persisted in the in-memory store so the status endpoint
  can serve cached results and resume can reconstruct failed inputs.
- A threading.Lock guards all mutations to the store dict, but individual BatchRecord
  fields are only mutated by one thread at a time (the processing loop), so no
  per-record locking is needed.
"""
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from app.config import config
from app.exceptions import BatchNotFoundError, BatchNotResumableError, ExternalAPIError
from app.models.batch import (
    BatchRecord,
    BatchStatus,
    HospitalInput,
    HospitalRecord,
    HospitalRecordStatus,
)
from app.services import hospital_client

logger = logging.getLogger(__name__)

_store: Dict[str, BatchRecord] = {}
_store_lock = threading.Lock()

# Statuses from which a batch can be resumed
_RESUMABLE_STATUSES = {BatchStatus.FAILED, BatchStatus.PARTIALLY_FAILED}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_bulk(hospitals: List[HospitalInput]) -> BatchRecord:
    """Create all hospitals concurrently, activate the batch, and return the result."""
    batch = _init_batch(hospitals)
    _run_processing(batch, hospitals)
    return batch


def get_batch(batch_id: str) -> BatchRecord:
    with _store_lock:
        batch = _store.get(batch_id)
    if batch is None:
        raise BatchNotFoundError(batch_id)
    return batch


def resume_batch(batch_id: str) -> BatchRecord:
    """Retry failed hospitals in an existing batch, then re-attempt activation."""
    batch = get_batch(batch_id)

    if batch.status not in _RESUMABLE_STATUSES:
        raise BatchNotResumableError(batch_id, batch.status.value)

    failed_indices = [
        record.row - 1  # row is 1-indexed; inputs list is 0-indexed
        for record in batch.hospitals
        if record.status == HospitalRecordStatus.FAILED
    ]

    if not failed_indices:
        # All records created but activation may have failed — just re-activate
        _attempt_activation(batch)
        return batch

    # Reset failed records so they can be re-processed
    for record in batch.hospitals:
        if record.status == HospitalRecordStatus.FAILED:
            record.status = HospitalRecordStatus.PENDING
            record.error = None

    failed_inputs = [batch.hospital_inputs[i] for i in failed_indices]
    _run_processing(batch, failed_inputs, resume_indices=failed_indices)
    return batch


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _init_batch(hospitals: List[HospitalInput]) -> BatchRecord:
    batch_id = str(uuid.uuid4())
    records = [HospitalRecord(row=i + 1, name=h.name) for i, h in enumerate(hospitals)]
    batch = BatchRecord(
        batch_id=batch_id,
        hospital_inputs=hospitals,
        hospitals=records,
        total_hospitals=len(hospitals),
    )
    with _store_lock:
        _store[batch_id] = batch
    return batch


def _run_processing(
    batch: BatchRecord,
    inputs: List[HospitalInput],
    resume_indices: Optional[List[int]] = None,
) -> None:
    """
    Fire concurrent POST /hospitals/ calls then activate the batch.

    `resume_indices` maps positions in `inputs` back to positions in
    `batch.hospitals` so partial retries update the correct records.
    """
    batch.status = BatchStatus.PROCESSING
    batch.started_at = time.time()
    batch.completed_at = None

    index_map = resume_indices or list(range(len(inputs)))

    results: List[Tuple[int, Optional[Dict], Optional[str]]] = []

    def _create(pos: int, hospital: HospitalInput) -> Tuple[int, Optional[Dict], Optional[str]]:
        try:
            data = hospital_client.create_hospital(hospital, batch.batch_id)
            return pos, data, None
        except ExternalAPIError as exc:
            return pos, None, str(exc)

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        futures = {pool.submit(_create, i, h): i for i, h in enumerate(inputs)}
        for future in as_completed(futures):
            results.append(future.result())

    # Apply results — done outside the executor to avoid any concurrent dict mutation
    created_count = 0
    failed_count = 0

    for local_pos, data, error in results:
        record_idx = index_map[local_pos]
        record = batch.hospitals[record_idx]

        if data is not None:
            record.hospital_id = data.get("id")
            record.status = HospitalRecordStatus.CREATED
            created_count += 1
        else:
            record.status = HospitalRecordStatus.FAILED
            record.error = error
            failed_count += 1

    # Re-count totals from the full record list (handles resume correctly)
    all_created = sum(
        1 for r in batch.hospitals if r.status in (
            HospitalRecordStatus.CREATED, HospitalRecordStatus.CREATED_AND_ACTIVATED
        )
    )
    all_failed = sum(1 for r in batch.hospitals if r.status == HospitalRecordStatus.FAILED)

    batch.processed_hospitals = all_created + all_failed
    batch.failed_hospitals = all_failed

    if all_created == 0:
        batch.status = BatchStatus.FAILED
        batch.completed_at = time.time()
        logger.error("Batch %s: all %d hospitals failed", batch.batch_id, len(inputs))
        return

    # Per spec: only activate when all hospitals were created successfully
    if all_failed == 0:
        _attempt_activation(batch)
    else:
        logger.warning(
            "Batch %s: %d/%d hospitals failed — skipping activation",
            batch.batch_id, all_failed, batch.total_hospitals,
        )

    batch.status = BatchStatus.COMPLETED if all_failed == 0 else BatchStatus.PARTIALLY_FAILED
    batch.completed_at = time.time()

    logger.info(
        "Batch %s done — created=%d failed=%d activated=%s elapsed=%.2fs",
        batch.batch_id, all_created, all_failed, batch.batch_activated,
        batch.processing_time_seconds,
    )


def _attempt_activation(batch: BatchRecord) -> None:
    batch.status = BatchStatus.ACTIVATING
    try:
        hospital_client.activate_batch(batch.batch_id)
        batch.batch_activated = True
        for record in batch.hospitals:
            if record.status == HospitalRecordStatus.CREATED:
                record.status = HospitalRecordStatus.CREATED_AND_ACTIVATED
        logger.info("Batch %s activated successfully", batch.batch_id)
    except ExternalAPIError as exc:
        batch.error = str(exc)
        logger.error("Batch %s activation failed: %s", batch.batch_id, exc)
