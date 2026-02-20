class ArchiveProcessingError(Exception):
    """Top-level error for the process_archive entry point."""

    pass


class UnsupportedProviderError(ValueError):
    """Raised when an unknown provider is requested."""

    pass
