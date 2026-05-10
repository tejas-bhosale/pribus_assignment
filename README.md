# Hospital Bulk Processing Service

A Flask microservice that accepts CSV uploads and bulk-creates hospitals in the [Hospital Directory API](https://hospital-directory.onrender.com/docs), using concurrent HTTP requests for performance.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/hospitals/bulk` | Upload CSV, create & activate all hospitals |
| `GET` | `/hospitals/bulk/{batch_id}/status` | Poll or retrieve a batch result |
| `POST` | `/hospitals/bulk/{batch_id}/resume` | Retry failed hospitals in a batch |
| `POST` | `/hospitals/validate` | Validate CSV format without processing |

### POST `/hospitals/bulk`

**Request:** `multipart/form-data` with a `file` field containing a CSV.

CSV format:
```
name,address,phone
General Hospital,123 Main St,555-1234
City Clinic,456 Oak Ave,
```

- `name` and `address` are required; `phone` is optional.  
- Maximum **20 hospitals** per upload.

**Response `200`:**
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "total_hospitals": 2,
  "processed_hospitals": 2,
  "failed_hospitals": 0,
  "processing_time_seconds": 1.45,
  "batch_activated": true,
  "hospitals": [
    { "row": 1, "hospital_id": 101, "name": "General Hospital", "status": "created_and_activated" }
  ]
}
```

Possible `status` values: `pending`, `processing`, `activating`, `completed`, `partially_failed`, `failed`.

> Activation is only attempted when **all** hospitals are created successfully, matching the upstream API's batch semantics.

### POST `/hospitals/validate`

Same `multipart/form-data` request as `/bulk`. Returns `200` if valid, `422` if not — no hospitals are created.

### POST `/hospitals/bulk/{batch_id}/resume`

Retries all `failed` hospital records in the given batch, then re-attempts activation. Returns `409` if the batch is not in a resumable state.

---

## Processing Design

Hospital creation calls are fired **concurrently** via `ThreadPoolExecutor` (default: 10 workers), reducing wall-clock time from `N × RTT` to roughly `1 × RTT`. The HTTP session uses automatic retries with exponential back-off for transient server errors.

---

## Running Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # edit if needed
python wsgi.py
```

The API is available at `http://localhost:5000`.

### Running with Docker

```bash
docker compose up --build
```

### Running Tests

```bash
pip install -r requirements.txt
pytest -v
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOSPITAL_API_BASE_URL` | `https://hospital-directory.onrender.com` | Base URL of the Hospital Directory API |
| `MAX_BATCH_SIZE` | `20` | Maximum hospitals per CSV |
| `MAX_WORKERS` | `10` | Concurrent threads for hospital creation |
| `REQUEST_TIMEOUT` | `30` | Per-request timeout in seconds |
| `DEBUG` | `false` | Enable Flask debug mode |

---

## Project Structure

```
.
├── app/
│   ├── __init__.py          # App factory, error handlers
│   ├── config.py            # Environment-based config
│   ├── exceptions.py        # Typed exception hierarchy
│   ├── models/
│   │   └── batch.py         # BatchRecord, HospitalRecord dataclasses
│   ├── routes/
│   │   └── hospitals.py     # Route handlers (thin controllers)
│   ├── services/
│   │   ├── batch_service.py # Orchestration logic
│   │   └── hospital_client.py # HTTP client for Hospital Directory API
│   └── utils/
│       └── csv_parser.py    # CSV parsing and validation
├── tests/
│   ├── conftest.py
│   ├── test_csv_parser.py
│   ├── test_batch_service.py
│   └── test_routes.py
├── wsgi.py
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```
