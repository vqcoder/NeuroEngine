import {
  DEFAULT_VIDEO_LIBRARY,
  WATCHLAB_LIBRARY_ID,
  buildStudyHref,
  isHttpUrl,
  isLikelyDirectVideoUrl,
  makeVideoLibraryItem,
  readVideoLibrary,
  resolveLibraryStudy,
  writeVideoLibrary,
  type VideoLibraryItem
} from '@/lib/videoLibrary';

class MockStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return [...this.store.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
}

describe('videoLibrary helpers', () => {
  test('accepts only http(s) URLs', () => {
    expect(isHttpUrl('https://cdn.example.com/demo.mp4')).toBe(true);
    expect(isHttpUrl('http://cdn.example.com/demo.mp4')).toBe(true);
    expect(isHttpUrl('ftp://cdn.example.com/demo.mp4')).toBe(false);
    expect(isHttpUrl('/sample.mp4')).toBe(false);
  });

  test('identifies direct playable video links', () => {
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/demo.mp4')).toBe(true);
    expect(isLikelyDirectVideoUrl('https://cdn.example.com/playlist.m3u8?token=1')).toBe(true);
    expect(isLikelyDirectVideoUrl('https://vimeo.com/123456')).toBe(false);
  });

  test('creates unique study ids when titles collide', () => {
    const baseItems: VideoLibraryItem[] = [
      {
        id: '1',
        title: 'Brand Film',
        studyId: 'brand-film',
        videoUrl: 'https://cdn.example.com/a.mp4',
        createdAt: new Date().toISOString()
      }
    ];

    const created = makeVideoLibraryItem(
      {
        title: 'Brand Film',
        videoUrl: 'https://cdn.example.com/b.mp4'
      },
      baseItems
    );

    expect(created.studyId).toBe('brand-film-2');
  });

  test('builds sequence study href with library metadata', () => {
    const href = buildStudyHref(
      {
        id: '1',
        title: 'My Spot',
        studyId: 'my-spot',
        videoUrl: 'https://cdn.example.com/spot.mp4',
        createdAt: new Date().toISOString()
      },
      3
    );

    expect(href.startsWith('/study/my-spot?')).toBe(true);
    const [, query = ''] = href.split('?');
    const params = new URLSearchParams(query);
    expect(params.get('library')).toBe(WATCHLAB_LIBRARY_ID);
    expect(params.get('index')).toBe('3');
    expect(params.get('video_url')).toBe('https://cdn.example.com/spot.mp4');
    expect(params.get('title')).toBe('My Spot');
    expect(params.get('entry_id')).toBe('1');
  });

  test('round-trips library items through storage', () => {
    const storage = new MockStorage();
    const items: VideoLibraryItem[] = [
      {
        id: '1',
        title: 'A',
        studyId: 'a',
        videoUrl: 'https://cdn.example.com/a.mp4',
        createdAt: new Date().toISOString()
      }
    ];

    writeVideoLibrary(storage, items);
    expect(readVideoLibrary(storage)).toEqual(items);
  });

  test('migrates legacy Railway asset URLs to same-origin proxy paths', () => {
    const storage = new MockStorage();
    const items: VideoLibraryItem[] = [
      {
        id: 'legacy-1',
        title: 'Legacy Proxy Asset',
        studyId: 'legacy-proxy-asset',
        videoUrl: 'https://biograph-api-production.up.railway.app/video-assets/kalshi-1.mp4?token=abc123',
        originalUrl: 'https://vimeo.com/123456789',
        createdAt: new Date().toISOString()
      }
    ];

    writeVideoLibrary(storage, items);
    const migrated = readVideoLibrary(storage);

    expect(migrated).toHaveLength(1);
    expect(migrated[0].videoUrl).toBe('/api/video-assets/kalshi-1.mp4?token=abc123');
    expect(migrated[0].originalUrl).toBe('https://vimeo.com/123456789');
  });

  test('migrates GitHub release asset URLs to same-origin proxy paths', () => {
    const storage = new MockStorage();
    const items: VideoLibraryItem[] = [
      {
        id: 'legacy-gh-1',
        title: 'Legacy GitHub Asset',
        studyId: 'legacy-github-asset',
        videoUrl:
          'https://github.com/johnvqcapital/neurotrace/releases/download/video-assets/codex-sample-check.mp4',
        originalUrl: 'https://cdn.example.com/original-source.mp4',
        createdAt: new Date().toISOString()
      }
    ];

    writeVideoLibrary(storage, items);
    const migrated = readVideoLibrary(storage);

    expect(migrated).toHaveLength(1);
    expect(migrated[0].videoUrl).toBe('/api/video-assets/codex-sample-check.mp4');
    expect(migrated[0].originalUrl).toBe('https://cdn.example.com/original-source.mp4');
  });

  test('pins default study entries to mp4 when legacy HLS URL is present', () => {
    const storage = new MockStorage();
    const items: VideoLibraryItem[] = [
      {
        id: 'legacy-default-kalshi-1',
        title: 'Kalshi Ad 1',
        studyId: 'kalshi-ad-1',
        videoUrl: 'https://cdn.example.com/kalshi-1/master.m3u8?token=abc',
        createdAt: new Date().toISOString()
      }
    ];

    writeVideoLibrary(storage, items);
    const migrated = readVideoLibrary(storage);
    const defaultKalshi = DEFAULT_VIDEO_LIBRARY.find((entry) => entry.studyId === 'kalshi-ad-1');

    expect(defaultKalshi).toBeDefined();
    expect(migrated).toHaveLength(1);
    expect(migrated[0].videoUrl).toBe(defaultKalshi?.videoUrl);
    expect(migrated[0].originalUrl).toBe('https://cdn.example.com/kalshi-1/master.m3u8?token=abc');
  });

  test('resolves by preferred index when study id matches', () => {
    const items: VideoLibraryItem[] = [
      {
        id: '1',
        title: 'First',
        studyId: 'first',
        videoUrl: 'https://cdn.example.com/first.mp4',
        createdAt: new Date().toISOString()
      },
      {
        id: '2',
        title: 'Why HomeAway',
        studyId: 'why-homeaway',
        videoUrl: 'https://cdn.example.com/why-homeaway.mp4',
        createdAt: new Date().toISOString()
      }
    ];

    const resolved = resolveLibraryStudy(items, 'why-homeaway', 1);
    expect(resolved).not.toBeNull();
    expect(resolved?.index).toBe(1);
    expect(resolved?.item.videoUrl).toBe('https://cdn.example.com/why-homeaway.mp4');
  });

  test('falls back to study id lookup when preferred index is stale', () => {
    const items: VideoLibraryItem[] = [
      {
        id: '1',
        title: 'Why HomeAway',
        studyId: 'why-homeaway',
        videoUrl: 'https://cdn.example.com/why-homeaway.mp4',
        createdAt: new Date().toISOString()
      },
      {
        id: '2',
        title: 'Other',
        studyId: 'other',
        videoUrl: 'https://cdn.example.com/other.mp4',
        createdAt: new Date().toISOString()
      }
    ];

    const resolved = resolveLibraryStudy(items, 'why-homeaway', 1);
    expect(resolved).not.toBeNull();
    expect(resolved?.index).toBe(0);
    expect(resolved?.item.title).toBe('Why HomeAway');
  });

  test('resolves by preferred id even when index is stale', () => {
    const items: VideoLibraryItem[] = [
      {
        id: 'first-id',
        title: 'Why HomeAway',
        studyId: 'why-homeaway',
        videoUrl: 'https://cdn.example.com/why-homeaway.mp4',
        createdAt: new Date().toISOString()
      },
      {
        id: 'second-id',
        title: 'Different',
        studyId: 'different',
        videoUrl: 'https://cdn.example.com/different.mp4',
        createdAt: new Date().toISOString()
      }
    ];

    const resolved = resolveLibraryStudy(items, 'why-homeaway', 1, 'first-id');
    expect(resolved).not.toBeNull();
    expect(resolved?.index).toBe(0);
    expect(resolved?.item.videoUrl).toBe('https://cdn.example.com/why-homeaway.mp4');
  });
});
