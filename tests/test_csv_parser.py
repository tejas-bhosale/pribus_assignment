import io
import pytest
from werkzeug.datastructures import FileStorage

from app.exceptions import CSVValidationError
from app.utils.csv_parser import parse_csv, validate_csv


def _make_file(content: str, filename: str = "test.csv") -> FileStorage:
    return FileStorage(
        stream=io.BytesIO(content.encode()),
        filename=filename,
        content_type="text/csv",
    )


class TestParseCsv:
    def test_valid_with_phone(self):
        f = _make_file("name,address,phone\nGeneral Hospital,123 Main St,555-1234")
        hospitals = parse_csv(f)
        assert len(hospitals) == 1
        assert hospitals[0].name == "General Hospital"
        assert hospitals[0].address == "123 Main St"
        assert hospitals[0].phone == "555-1234"

    def test_valid_without_phone(self):
        f = _make_file("name,address\nGeneral Hospital,123 Main St")
        hospitals = parse_csv(f)
        assert hospitals[0].phone is None

    def test_empty_phone_treated_as_none(self):
        f = _make_file("name,address,phone\nGeneral Hospital,123 Main St,")
        hospitals = parse_csv(f)
        assert hospitals[0].phone is None

    def test_multiple_rows(self):
        content = "name,address\nHospital A,Addr A\nHospital B,Addr B\nHospital C,Addr C"
        f = _make_file(content)
        hospitals = parse_csv(f)
        assert len(hospitals) == 3

    def test_strips_whitespace(self):
        f = _make_file("name,address\n  City Hospital  ,  456 Oak Ave  ")
        hospitals = parse_csv(f)
        assert hospitals[0].name == "City Hospital"
        assert hospitals[0].address == "456 Oak Ave"

    def test_missing_name_column_raises(self):
        f = _make_file("address,phone\n123 Main St,555-1234")
        with pytest.raises(CSVValidationError, match="Missing required columns"):
            parse_csv(f)

    def test_missing_address_column_raises(self):
        f = _make_file("name\nGeneral Hospital")
        with pytest.raises(CSVValidationError, match="Missing required columns"):
            parse_csv(f)

    def test_blank_name_raises(self):
        f = _make_file("name,address\n,123 Main St")
        with pytest.raises(CSVValidationError, match="'name' is required"):
            parse_csv(f)

    def test_blank_address_raises(self):
        f = _make_file("name,address\nGeneral Hospital,")
        with pytest.raises(CSVValidationError, match="'address' is required"):
            parse_csv(f)

    def test_empty_file_raises(self):
        f = _make_file("")
        with pytest.raises(CSVValidationError):
            parse_csv(f)

    def test_no_data_rows_raises(self):
        f = _make_file("name,address")
        with pytest.raises(CSVValidationError, match="no data rows"):
            parse_csv(f)

    def test_exceeds_max_size_raises(self):
        rows = "\n".join(f"Hospital {i},Address {i}" for i in range(21))
        f = _make_file(f"name,address\n{rows}")
        with pytest.raises(CSVValidationError, match="limit"):
            parse_csv(f)

    def test_wrong_extension_raises(self):
        f = _make_file("name,address\nHospital A,Addr A", filename="data.txt")
        with pytest.raises(CSVValidationError, match=".csv"):
            parse_csv(f)

    def test_non_utf8_raises(self):
        raw = b"name,address\nH\xf6spital,Addr"
        fs = FileStorage(stream=io.BytesIO(raw), filename="test.csv", content_type="text/csv")
        with pytest.raises(CSVValidationError, match="UTF-8"):
            parse_csv(fs)


class TestValidateCsv:
    def test_valid_csv_returns_valid_true(self):
        f = _make_file("name,address\nGeneral Hospital,123 Main St")
        report = validate_csv(f)
        assert report["valid"] is True
        assert report["total_rows"] == 1
        assert report["errors"] == []

    def test_unknown_column_produces_warning(self):
        f = _make_file("name,address,foo\nGeneral Hospital,123 Main St,bar")
        report = validate_csv(f)
        assert any("foo" in w for w in report["warnings"])

    def test_invalid_rows_reported(self):
        content = "name,address\nGeneral Hospital,123 Main St\n,456 Oak Ave\nCity Hospital,"
        f = _make_file(content)
        report = validate_csv(f)
        assert report["valid"] is False
        invalid_rows = [r for r in report["rows"] if not r["valid"]]
        assert len(invalid_rows) == 2

    def test_over_limit_reports_error(self):
        rows = "\n".join(f"Hospital {i},Address {i}" for i in range(21))
        f = _make_file(f"name,address\n{rows}")
        report = validate_csv(f)
        assert report["valid"] is False
        assert any("limit" in e for e in report["errors"])
