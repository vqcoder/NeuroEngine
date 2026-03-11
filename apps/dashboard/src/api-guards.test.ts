import { describe, it, expect } from 'vitest';
import {
  ApiShapeMismatchError,
  guardIsObject,
  guardHasField,
  guardItemsWrapper,
  guardReadoutShape,
} from './api-guards';

// ---------------------------------------------------------------------------
// guardIsObject
// ---------------------------------------------------------------------------
describe('guardIsObject', () => {
  it('accepts a plain object', () => {
    expect(() => guardIsObject({ a: 1 }, '/test')).not.toThrow();
  });

  it('accepts an empty object', () => {
    expect(() => guardIsObject({}, '/test')).not.toThrow();
  });

  it('rejects null', () => {
    expect(() => guardIsObject(null, '/test')).toThrow(ApiShapeMismatchError);
    expect(() => guardIsObject(null, '/test')).toThrow('expected object, got null');
  });

  it('rejects arrays', () => {
    expect(() => guardIsObject([1, 2], '/test')).toThrow(ApiShapeMismatchError);
    expect(() => guardIsObject([1, 2], '/test')).toThrow('expected object, got array');
  });

  it('rejects primitives', () => {
    expect(() => guardIsObject('hello', '/test')).toThrow('expected object, got string');
    expect(() => guardIsObject(42, '/test')).toThrow('expected object, got number');
    expect(() => guardIsObject(undefined, '/test')).toThrow('expected object, got undefined');
    expect(() => guardIsObject(true, '/test')).toThrow('expected object, got boolean');
  });

  it('includes endpoint in error message', () => {
    expect(() => guardIsObject(null, 'GET /videos')).toThrow('API shape mismatch on GET /videos');
  });
});

// ---------------------------------------------------------------------------
// guardHasField
// ---------------------------------------------------------------------------
describe('guardHasField', () => {
  it('passes when field exists', () => {
    expect(() => guardHasField({ items: [] }, 'items', '/test')).not.toThrow();
  });

  it('passes when field exists with falsy value', () => {
    expect(() => guardHasField({ count: 0 }, 'count', '/test')).not.toThrow();
    expect(() => guardHasField({ name: '' }, 'name', '/test')).not.toThrow();
    expect(() => guardHasField({ data: null }, 'data', '/test')).not.toThrow();
  });

  it('rejects missing field', () => {
    expect(() => guardHasField({ other: 1 }, 'items', '/test')).toThrow(ApiShapeMismatchError);
    expect(() => guardHasField({ other: 1 }, 'items', '/test')).toThrow('missing required field "items"');
  });
});

// ---------------------------------------------------------------------------
// guardItemsWrapper
// ---------------------------------------------------------------------------
describe('guardItemsWrapper', () => {
  it('returns the items array', () => {
    const items = [{ id: 1 }, { id: 2 }];
    expect(guardItemsWrapper({ items }, '/test')).toBe(items);
  });

  it('returns empty array', () => {
    expect(guardItemsWrapper({ items: [] }, '/test')).toEqual([]);
  });

  it('rejects non-object input', () => {
    expect(() => guardItemsWrapper([1, 2], '/test')).toThrow('expected object, got array');
  });

  it('rejects object without items field', () => {
    expect(() => guardItemsWrapper({ data: [] }, '/test')).toThrow('missing required field "items"');
  });

  it('rejects non-array items', () => {
    expect(() => guardItemsWrapper({ items: 'not-array' }, '/test')).toThrow('"items" is not an array');
    expect(() => guardItemsWrapper({ items: {} }, '/test')).toThrow('"items" is not an array');
  });
});

// ---------------------------------------------------------------------------
// guardReadoutShape
// ---------------------------------------------------------------------------
describe('guardReadoutShape', () => {
  const validReadout = {
    video_id: 'abc',
    traces: { attention_score: [] },
    segments: { attention_gain_segments: [] },
  };

  it('accepts valid readout shape', () => {
    expect(() => guardReadoutShape(validReadout, '/test')).not.toThrow();
  });

  it('accepts readout with extra fields', () => {
    expect(() => guardReadoutShape({ ...validReadout, extra: true }, '/test')).not.toThrow();
  });

  it('rejects non-object', () => {
    expect(() => guardReadoutShape(null, '/test')).toThrow('expected object');
  });

  it('rejects missing video_id', () => {
    const { video_id: _, ...rest } = validReadout;
    expect(() => guardReadoutShape(rest, '/test')).toThrow('missing required field "video_id"');
  });

  it('rejects missing traces', () => {
    const { traces: _, ...rest } = validReadout;
    expect(() => guardReadoutShape(rest, '/test')).toThrow('missing required field "traces"');
  });

  it('rejects missing segments', () => {
    const { segments: _, ...rest } = validReadout;
    expect(() => guardReadoutShape(rest, '/test')).toThrow('missing required field "segments"');
  });

  it('rejects null traces', () => {
    expect(() => guardReadoutShape({ ...validReadout, traces: null }, '/test')).toThrow(
      '"traces" is not an object'
    );
  });

  it('rejects array traces', () => {
    expect(() => guardReadoutShape({ ...validReadout, traces: [] }, '/test')).toThrow(
      '"traces" is not an object'
    );
  });
});
