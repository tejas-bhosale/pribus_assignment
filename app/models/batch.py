import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class BatchStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    ACTIVATING = "activating"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"


class HospitalRecordStatus(str, Enum):
    PENDING = "pending"
    CREATED = "created"
    CREATED_AND_ACTIVATED = "created_and_activated"
    FAILED = "failed"


@dataclass
class HospitalInput:
    name: str
    address: str
    phone: Optional[str] = None


@dataclass
class HospitalRecord:
    row: int
    name: str
    status: HospitalRecordStatus = HospitalRecordStatus.PENDING
    hospital_id: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "row": self.row,
            "name": self.name,
            "status": self.status.value,
        }
        if self.hospital_id is not None:
            d["hospital_id"] = self.hospital_id
        if self.error is not None:
            d["error"] = self.error
        return d


@dataclass
class BatchRecord:
    batch_id: str
    # Retained to support resume without re-uploading the CSV
    hospital_inputs: List[HospitalInput]
    hospitals: List[HospitalRecord]
    total_hospitals: int
    status: BatchStatus = BatchStatus.PENDING
    processed_hospitals: int = 0
    failed_hospitals: int = 0
    batch_activated: bool = False
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def processing_time_seconds(self) -> float:
        end = self.completed_at or time.time()
        return round(end - self.started_at, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "total_hospitals": self.total_hospitals,
            "processed_hospitals": self.processed_hospitals,
            "failed_hospitals": self.failed_hospitals,
            "processing_time_seconds": self.processing_time_seconds,
            "batch_activated": self.batch_activated,
            "hospitals": [h.to_dict() for h in self.hospitals],
        }
