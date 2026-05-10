class BulkProcessingError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class CSVValidationError(BulkProcessingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class BatchNotFoundError(BulkProcessingError):
    def __init__(self, batch_id: str) -> None:
        super().__init__(f"Batch '{batch_id}' not found", status_code=404)


class BatchNotResumableError(BulkProcessingError):
    def __init__(self, batch_id: str, current_status: str) -> None:
        super().__init__(
            f"Batch '{batch_id}' is not resumable (status: {current_status}). "
            "Only 'failed' or 'partially_failed' batches can be resumed.",
            status_code=409,
        )


class ExternalAPIError(BulkProcessingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=502)
