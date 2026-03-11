/**
 * Shared URL utility helpers for WatchLab server-side route handlers.
 *
 * Client-side code should import from `lib/videoLibrary` instead.
 */

export const isHttpUrl = (value: string): boolean => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};
