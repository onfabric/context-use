"""Custom exceptions for ETL pipeline operations."""


class ExtractionFailedException(Exception):
    def __init__(self, message: str | None = None):
        self.message = (
            f"Extraction failed: {message}" if message else "Extraction failed"
        )
        super().__init__(self.message)


class TransformFailedException(Exception):
    def __init__(self, message: str | None = None):
        self.message = f"Transform failed: {message}" if message else "Transform failed"
        super().__init__(self.message)


class UploadFailedException(Exception):
    def __init__(self, message: str | None = None):
        self.message = f"Upload failed: {message}" if message else "Upload failed"
        super().__init__(self.message)


class UnknownDataPatternException(Exception):
    """Raised when a ThreadPayloadBuilder encounters unknown/unmatched data pattern."""

    def __init__(
        self,
        unknown_value: str,
        builder_class: str,
        message: str | None = None,
    ):
        self.unknown_value = unknown_value
        self.builder_class = builder_class
        self.message = (
            message or f"Unknown data pattern in {builder_class}: {unknown_value}"
        )
        super().__init__(self.message)


class ArchiveProcessingError(Exception):
    """Top-level error for the process_archive entry point."""

    pass


class UnsupportedProviderError(ValueError):
    """Raised when an unknown provider is requested."""

    pass
