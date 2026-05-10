import csv
import io
from typing import Any, Dict, List

from werkzeug.datastructures import FileStorage

from app.config import config
from app.exceptions import CSVValidationError
from app.models.batch import HospitalInput

REQUIRED_COLUMNS = {"name", "address"}
OPTIONAL_COLUMNS = {"phone"}
ALL_KNOWN_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


def parse_csv(file: FileStorage) -> List[HospitalInput]:
    """Parse and validate an uploaded CSV file, returning a list of HospitalInput objects."""
    _assert_valid_file(file)
    content = _read_file_content(file)
    return _parse_content(content)


def validate_csv(file: FileStorage) -> Dict[str, Any]:
    """Dry-run validation — returns a report without creating any hospitals."""
    _assert_valid_file(file)
    content = _read_file_content(file)

    errors: List[str] = []
    warnings: List[str] = []
    row_reports: List[Dict[str, Any]] = []

    try:
        reader = csv.DictReader(io.StringIO(content))
        headers = set(reader.fieldnames or [])

        missing = REQUIRED_COLUMNS - headers
        if missing:
            errors.append(f"Missing required columns: {', '.join(sorted(missing))}")

        unknown = headers - ALL_KNOWN_COLUMNS
        if unknown:
            warnings.append(f"Unknown columns will be ignored: {', '.join(sorted(unknown))}")

        rows = list(reader)
        if not rows:
            errors.append("CSV contains no data rows")

        if len(rows) > config.MAX_BATCH_SIZE:
            errors.append(
                f"CSV exceeds the {config.MAX_BATCH_SIZE}-hospital limit (found {len(rows)})"
            )

        for i, row in enumerate(rows, start=1):
            row_errors = _validate_row(row, i)
            row_reports.append({"row": i, "valid": not row_errors, "errors": row_errors})

    except Exception as exc:
        errors.append(f"Failed to parse CSV: {exc}")

    invalid_row_count = sum(1 for r in row_reports if not r["valid"])
    if invalid_row_count:
        errors.append(f"{invalid_row_count} row(s) have validation errors (see 'rows' for details)")
    return {
        "valid": not errors,
        "total_rows": len(row_reports),
        "errors": errors,
        "warnings": warnings,
        "rows": row_reports,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_valid_file(file: FileStorage) -> None:
    if not file or not file.filename:
        raise CSVValidationError("No file provided")
    if not file.filename.lower().endswith(".csv"):
        raise CSVValidationError("File must have a .csv extension")


def _read_file_content(file: FileStorage) -> str:
    try:
        return file.stream.read().decode("utf-8")
    except UnicodeDecodeError:
        raise CSVValidationError("File must be UTF-8 encoded")


def _parse_content(content: str) -> List[HospitalInput]:
    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        raise CSVValidationError("CSV is empty or has no header row")

    headers = set(reader.fieldnames)
    missing = REQUIRED_COLUMNS - headers
    if missing:
        raise CSVValidationError(
            f"Missing required columns: {', '.join(sorted(missing))}"
        )

    rows = list(reader)
    if not rows:
        raise CSVValidationError("CSV contains no data rows")

    if len(rows) > config.MAX_BATCH_SIZE:
        raise CSVValidationError(
            f"CSV exceeds the {config.MAX_BATCH_SIZE}-hospital limit (found {len(rows)})"
        )

    hospitals: List[HospitalInput] = []
    all_errors: List[str] = []

    for i, row in enumerate(rows, start=1):
        row_errors = _validate_row(row, i)
        if row_errors:
            all_errors.extend(row_errors)
        else:
            hospitals.append(
                HospitalInput(
                    name=row["name"].strip(),
                    address=row["address"].strip(),
                    phone=row.get("phone", "").strip() or None,
                )
            )

    if all_errors:
        raise CSVValidationError(
            f"CSV validation failed — {len(all_errors)} error(s): {'; '.join(all_errors)}"
        )

    return hospitals


def _validate_row(row: Dict[str, Any], row_num: int) -> List[str]:
    errors: List[str] = []
    if not row.get("name", "").strip():
        errors.append(f"Row {row_num}: 'name' is required and cannot be blank")
    if not row.get("address", "").strip():
        errors.append(f"Row {row_num}: 'address' is required and cannot be blank")
    return errors
