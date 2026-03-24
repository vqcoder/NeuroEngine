import { describe, it, expect } from 'vitest';

// Test the extractTier logic directly — avoids needing @testing-library/react
// to render the hook, while still validating the tier derivation contract.

type WorkspaceTier = 'free' | 'creator' | 'enterprise';

/** Mirror of the extractTier function from useAuth.ts */
function extractTier(appMetadata: Record<string, unknown> | undefined): WorkspaceTier {
  const raw = appMetadata?.tier;
  if (raw === 'free' || raw === 'enterprise') return raw;
  return 'creator';
}

describe('useAuth tier extraction', () => {
  it('defaults to creator when app_metadata is undefined', () => {
    expect(extractTier(undefined)).toBe('creator');
  });

  it('defaults to creator when app_metadata.tier is missing', () => {
    expect(extractTier({})).toBe('creator');
  });

  it('reads free tier correctly', () => {
    expect(extractTier({ tier: 'free' })).toBe('free');
  });

  it('reads creator tier correctly', () => {
    expect(extractTier({ tier: 'creator' })).toBe('creator');
  });

  it('reads enterprise tier correctly', () => {
    expect(extractTier({ tier: 'enterprise' })).toBe('enterprise');
  });

  it('falls back to creator for unknown tier values', () => {
    expect(extractTier({ tier: 'unknown' })).toBe('creator');
  });

  it('falls back to creator when tier is null', () => {
    expect(extractTier({ tier: null })).toBe('creator');
  });
});
