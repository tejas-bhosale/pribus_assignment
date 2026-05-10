import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    HOSPITAL_API_BASE_URL: str = os.getenv(
        "HOSPITAL_API_BASE_URL", "https://hospital-directory.onrender.com"
    )
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "20"))
    # Number of concurrent workers for hospital creation
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "10"))
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"


config = Config()
