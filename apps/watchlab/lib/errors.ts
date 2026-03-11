/**
 * Structured error taxonomy for WatchLab.
 * Provides machine-readable codes so retry logic, telemetry, and UI
 * can distinguish retryable vs. terminal failures without string parsing.
 */

export const UploadErrorCode = {
  /** Payload did not pass Zod schema validation — terminal, do not retry */
  SCHEMA_INVALID: 'SCHEMA_INVALID',
  /** Trace rows missing and synthetic fallback is disabled — terminal */
  MISSING_TRACE_ROWS: 'MISSING_TRACE_ROWS',
  /** HTTP 4xx from upload API — terminal (client error) */
  CLIENT_ERROR: 'CLIENT_ERROR',
  /** HTTP 5xx from upload API — retryable */
  SERVER_ERROR: 'SERVER_ERROR',
  /** Network failure (fetch threw, offline, timeout) — retryable */
  NETWORK_ERROR: 'NETWORK_ERROR',
  /** All retry attempts exhausted */
  RETRY_EXHAUSTED: 'RETRY_EXHAUSTED',
  /** Payload too large (413) — terminal */
  PAYLOAD_TOO_LARGE: 'PAYLOAD_TOO_LARGE',
} as const;

export type UploadErrorCode = (typeof UploadErrorCode)[keyof typeof UploadErrorCode];

export class WatchlabUploadError extends Error {
  readonly code: UploadErrorCode;
  readonly retryable: boolean;
  readonly httpStatus?: number;

  constructor(
    code: UploadErrorCode,
    message: string,
    options?: { retryable?: boolean; httpStatus?: number }
  ) {
    super(message);
    this.name = 'WatchlabUploadError';
    this.code = code;
    this.retryable = options?.retryable ?? false;
    this.httpStatus = options?.httpStatus;
  }
}

export const classifyHttpError = (status: number, message: string): WatchlabUploadError => {
  if (status === 413) {
    return new WatchlabUploadError(UploadErrorCode.PAYLOAD_TOO_LARGE, message, {
      retryable: false,
      httpStatus: status
    });
  }
  if (status >= 400 && status < 500) {
    return new WatchlabUploadError(UploadErrorCode.CLIENT_ERROR, message, {
      retryable: false,
      httpStatus: status
    });
  }
  if (status >= 500) {
    return new WatchlabUploadError(UploadErrorCode.SERVER_ERROR, message, {
      retryable: true,
      httpStatus: status
    });
  }
  return new WatchlabUploadError(UploadErrorCode.NETWORK_ERROR, message, { retryable: true });
};

export const WebcamErrorCode = {
  /** Browser does not support getUserMedia */
  NOT_SUPPORTED: 'NOT_SUPPORTED',
  /** User denied camera permission */
  PERMISSION_DENIED: 'PERMISSION_DENIED',
  /** Camera device was lost mid-session */
  DEVICE_LOST: 'DEVICE_LOST',
  /** Device not found (unplugged, driver issue) */
  DEVICE_NOT_FOUND: 'DEVICE_NOT_FOUND',
} as const;

export type WebcamErrorCode = (typeof WebcamErrorCode)[keyof typeof WebcamErrorCode];
