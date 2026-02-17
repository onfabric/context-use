/**
 * Custom exceptions for ETL pipeline operations.
 */

export class ExtractionFailedException extends Error {
  constructor(message?: string) {
    super(message ? `Extraction failed: ${message}` : "Extraction failed");
    this.name = "ExtractionFailedException";
  }
}

export class TransformFailedException extends Error {
  constructor(message?: string) {
    super(message ? `Transform failed: ${message}` : "Transform failed");
    this.name = "TransformFailedException";
  }
}

export class UploadFailedException extends Error {
  constructor(message?: string) {
    super(message ? `Upload failed: ${message}` : "Upload failed");
    this.name = "UploadFailedException";
  }
}

export class UnknownDataPatternException extends Error {
  unknownValue: string;
  builderClass: string;

  constructor(unknownValue: string, builderClass: string, message?: string) {
    super(
      message ??
        `Unknown data pattern in ${builderClass}: ${unknownValue}`,
    );
    this.name = "UnknownDataPatternException";
    this.unknownValue = unknownValue;
    this.builderClass = builderClass;
  }
}

export class ArchiveProcessingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ArchiveProcessingError";
  }
}

export class UnsupportedProviderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UnsupportedProviderError";
  }
}

