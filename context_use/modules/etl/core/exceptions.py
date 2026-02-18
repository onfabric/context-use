class ExtractionFailedException(Exception):
    pass


class TransformFailedException(Exception):
    pass


class UploadFailedException(Exception):
    pass


class ArchiveProcessingError(Exception):
    pass


class UnsupportedProviderError(Exception):
    pass


class UnknownDataPatternException(Exception):
    pass

