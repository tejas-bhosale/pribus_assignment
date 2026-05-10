"""Thin HTTP client for the Hospital Directory API.

Kept separate from business logic so it can be mocked cleanly in tests.
Retry logic is baked into the session so callers don't need to think about it.
"""
import logging
from typing import Any, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import config
from app.exceptions import ExternalAPIError
from app.models.batch import HospitalInput

logger = logging.getLogger(__name__)


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        # Retry on transient server errors and rate limits, not on 4xx client errors
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "PATCH", "GET", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# Module-level session reuse — keeps the connection pool warm across requests
_session = _build_session()


def create_hospital(hospital: HospitalInput, batch_id: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": hospital.name,
        "address": hospital.address,
        "creation_batch_id": batch_id,
    }
    if hospital.phone:
        payload["phone"] = hospital.phone

    try:
        resp = _session.post(
            f"{config.HOSPITAL_API_BASE_URL}/hospitals/",
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        body = exc.response.text[:200] if exc.response is not None else ""
        logger.warning("Hospital creation failed [%s]: %s", status, body)
        raise ExternalAPIError(
            f"Failed to create hospital '{hospital.name}' (HTTP {status})"
        ) from exc
    except requests.RequestException as exc:
        logger.error("Network error creating hospital '%s': %s", hospital.name, exc)
        raise ExternalAPIError(
            f"Network error while creating hospital '{hospital.name}': {exc}"
        ) from exc


def activate_batch(batch_id: str) -> Dict[str, Any]:
    try:
        resp = _session.patch(
            f"{config.HOSPITAL_API_BASE_URL}/hospitals/batch/{batch_id}/activate",
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        logger.error("Batch activation failed for %s [HTTP %s]", batch_id, status)
        raise ExternalAPIError(
            f"Failed to activate batch '{batch_id}' (HTTP {status})"
        ) from exc
    except requests.RequestException as exc:
        logger.error("Network error activating batch %s: %s", batch_id, exc)
        raise ExternalAPIError(
            f"Network error while activating batch '{batch_id}': {exc}"
        ) from exc
