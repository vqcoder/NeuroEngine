/**
 * Lightweight runtime guards for API response shapes.
 *
 * These catch structural mismatches (wrong wrapper, missing required fields)
 * that `as Type` compile-time casts cannot detect.  Intentionally permissive —
 * only top-level keys are checked so new optional fields never cause false
 * rejections.
 */

export class ApiShapeMismatchError extends Error {
  constructor(endpoint: string, detail: string) {
    super(`API shape mismatch on ${endpoint}: ${detail}`);
    this.name = 'ApiShapeMismatchError';
  }
}

/** Assert that `value` is a non-null, non-array object. */
export function guardIsObject(
  value: unknown,
  endpoint: string
): asserts value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiShapeMismatchError(
      endpoint,
      `expected object, got ${value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value}`
    );
  }
}

/** Assert that `obj` contains `field`. */
export function guardHasField<K extends string>(
  obj: Record<string, unknown>,
  field: K,
  endpoint: string
): asserts obj is Record<string, unknown> & Record<K, unknown> {
  if (!(field in obj)) {
    throw new ApiShapeMismatchError(endpoint, `missing required field "${field}"`);
  }
}

/** Assert `value` is `{ items: unknown[] }` and return the items array. */
export function guardItemsWrapper(value: unknown, endpoint: string): unknown[] {
  guardIsObject(value, endpoint);
  guardHasField(value, 'items', endpoint);
  if (!Array.isArray(value.items)) {
    throw new ApiShapeMismatchError(endpoint, `"items" is not an array`);
  }
  return value.items;
}

/** Guard the readout payload — checks the 3 keys whose absence causes crashes. */
export function guardReadoutShape(value: unknown, endpoint: string): void {
  guardIsObject(value, endpoint);
  guardHasField(value, 'video_id', endpoint);
  guardHasField(value, 'traces', endpoint);
  guardHasField(value, 'segments', endpoint);
  if (typeof value.traces !== 'object' || value.traces === null || Array.isArray(value.traces)) {
    throw new ApiShapeMismatchError(endpoint, `"traces" is not an object`);
  }
}
