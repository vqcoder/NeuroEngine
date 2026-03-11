import { expect, test, type Page } from '@playwright/test';

type UploadPayload = {
  eventTimeline: Array<{
    type: string;
    sessionId: string;
    videoId: string;
    videoTimeMs: number;
    clientMonotonicMs: number;
    wallTimeMs: number;
    details?: Record<string, unknown>;
  }>;
  annotations: Array<{
    markerType: 'engaging_moment' | 'confusing_moment' | 'stop_watching_moment' | 'cta_landed_moment';
    videoTimeMs: number;
    note?: string | null;
  }>;
  annotationSkipped: boolean;
  surveyResponses: Array<{
    questionKey: string;
    responseNumber?: number;
    responseText?: string;
    responseJson?: Record<string, unknown>;
  }>;
  traceRows: Array<{
    video_time_ms: number;
    quality_score?: number;
    tracking_confidence?: number;
  }>;
};

const installMediaMocks = async (page: Page) => {
  await page.addInitScript(() => {
    const nativePlay = HTMLMediaElement.prototype.play;
    const nativePause = HTMLMediaElement.prototype.pause;

    (window as Window & { __mockVisibilityState?: DocumentVisibilityState }).__mockVisibilityState =
      'visible';
    (window as Window & { __mockFullscreenElement?: Element | null }).__mockFullscreenElement = null;

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () =>
        (window as Window & { __mockVisibilityState?: DocumentVisibilityState }).__mockVisibilityState ??
        'visible'
    });

    Object.defineProperty(document, 'fullscreenElement', {
      configurable: true,
      get: () =>
        (window as Window & { __mockFullscreenElement?: Element | null }).__mockFullscreenElement ??
        null
    });

    const mediaDevices = navigator.mediaDevices ?? ({} as MediaDevices);
    mediaDevices.getUserMedia = async () => new MediaStream();
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: mediaDevices
    });

    HTMLMediaElement.prototype.play = function playPatched() {
      if (
        this instanceof HTMLVideoElement &&
        ['study-video', 'annotation-video'].includes(this.getAttribute('data-testid') ?? '')
      ) {
        const video = this as HTMLVideoElement & { __tickTimer?: number };
        if (video.__tickTimer) {
          window.clearInterval(video.__tickTimer);
        }
        video.dispatchEvent(new Event('play'));
        video.__tickTimer = window.setInterval(() => {
          video.currentTime += 0.1;
          video.dispatchEvent(new Event('timeupdate'));
        }, 100);
        return Promise.resolve();
      }

      if (this instanceof HTMLVideoElement && this.getAttribute('data-testid') === 'webcam-preview') {
        return Promise.resolve();
      }

      return nativePlay.call(this);
    };

    HTMLMediaElement.prototype.pause = function pausePatched() {
      if (
        this instanceof HTMLVideoElement &&
        ['study-video', 'annotation-video'].includes(this.getAttribute('data-testid') ?? '')
      ) {
        const video = this as HTMLVideoElement & { __tickTimer?: number };
        if (video.__tickTimer) {
          window.clearInterval(video.__tickTimer);
          video.__tickTimer = undefined;
        }
        video.dispatchEvent(new Event('pause'));
        return;
      }
      nativePause.call(this);
    };
  });
};

test.describe('watchlab smoke', () => {
  test('library upload enables one-click next study after video end', async ({ page }) => {
    await installMediaMocks(page);

    await page.goto('/upload');
    await page.getByTestId('upload-title-input').fill('First Spot');
    await page
      .getByTestId('upload-video-url-input')
      .fill('https://cdn.example.com/first-spot.mp4');
    await page.getByTestId('add-video-button').click();

    await page.getByTestId('upload-title-input').fill('Second Spot');
    await page
      .getByTestId('upload-video-url-input')
      .fill('https://cdn.example.com/second-spot.mp4');
    await page.getByTestId('add-video-button').click();

    await expect(page.getByTestId('library-item')).toHaveCount(2);
    await page.getByTestId('start-sequence-link').click();

    await expect(page.getByTestId('consent-screen')).toBeVisible();
    await page.getByTestId('agree-button').click();
    await page.getByTestId('audio-confirmed-checkbox').check();
    await page.getByTestId('start-watch-button').click();
    await expect(page.getByTestId('watch-stage')).toBeVisible();

    await page.evaluate(() => {
      const video = document.querySelector('[data-testid=\"study-video\"]') as HTMLVideoElement | null;
      if (!video) {
        return;
      }
      video.currentTime = 1.8;
      video.dispatchEvent(new Event('ended'));
    });

    await expect(page.getByTestId('survey-stage')).toBeVisible();
    await page.getByTestId('survey-overall-engagement-input').fill('4');
    await page.getByTestId('survey-content-clarity-input').fill('4');
    await page.getByTestId('finish-button').click();
    const nextStudyLink = page.getByTestId('completion-next-study-link');
    await expect(nextStudyLink).toBeVisible();
    await expect(nextStudyLink).toHaveAttribute('href', /\/study\/second-spot\?/);
    await nextStudyLink.click();

    await expect(page).toHaveURL(/\/study\/second-spot\?/);
    await expect(page.getByTestId('consent-screen')).toBeVisible();
  });

  test('upload resolves webpage links into playable library entries', async ({ page }) => {
    await installMediaMocks(page);

    await page.route('**/api/video/resolve', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          inputUrl: 'https://vimeo.com/176228082',
          resolvedUrl: 'https://cdn.example.com/why-homeaway.mp4',
          videoUrl: 'https://cdn.example.com/why-homeaway.mp4',
          strategy: 'vimeo-progressive',
          downloaded: false
        })
      });
    });

    await page.goto('/upload');
    await page.getByTestId('upload-title-input').fill('why-homeaway');
    await page.getByTestId('upload-video-url-input').fill('https://vimeo.com/176228082');
    await page.getByTestId('add-video-button').click();

    await expect(page.getByTestId('library-item')).toHaveCount(1);
    await expect(page.getByText('https://cdn.example.com/why-homeaway.mp4')).toBeVisible();
  });

  test('consent gating works', async ({ page }) => {
    await installMediaMocks(page);
    await page.goto('/study/demo');

    await expect(page.getByTestId('consent-screen')).toBeVisible();
    await expect(page.getByTestId('study-shell')).toHaveCount(0);

    await page.getByTestId('agree-button').click();
    await expect(page.getByTestId('study-shell')).toBeVisible();
    await expect(page.getByTestId('camera-stage')).toBeVisible();
    await expect(page.getByTestId('face-detector-compatibility-note')).toHaveCount(0);
    await expect(page.getByText('Face detection API is unavailable in this browser.')).toHaveCount(0);
    await expect(page.getByTestId('start-watch-button')).toBeDisabled();
    await page.getByTestId('audio-confirmed-checkbox').check();
    await expect(page.getByTestId('start-watch-button')).toBeEnabled();
  });

  test('camera stage allows proceeding without webcam when study is optional', async ({ page }) => {
    await installMediaMocks(page);
    await page.addInitScript(() => {
      const mediaDevices = navigator.mediaDevices ?? ({} as MediaDevices);
      mediaDevices.getUserMedia = async () => {
        throw new Error('permission denied');
      };
      Object.defineProperty(navigator, 'mediaDevices', {
        configurable: true,
        value: mediaDevices
      });
    });

    await page.goto('/study/demo');
    await page.getByTestId('agree-button').click();
    await expect(page.getByTestId('camera-stage')).toBeVisible();
    await expect(page.getByTestId('continue-without-webcam-button')).toBeVisible();
    await page.getByTestId('continue-without-webcam-button').click();
    await expect(page.getByTestId('webcam-bypassed-note')).toBeVisible();

    await page.getByTestId('audio-confirmed-checkbox').check();
    await expect(page.getByTestId('start-watch-button')).toBeEnabled();
    await page.getByTestId('start-watch-button').click();
    await expect(page.getByTestId('watch-stage')).toBeVisible();
  });

  test('videoTimeMs is monotonic during playback', async ({ page }) => {
    await installMediaMocks(page);

    await page.goto('/study/demo');
    await page.getByTestId('agree-button').click();
    await page.getByTestId('audio-confirmed-checkbox').check();
    await page.getByTestId('start-watch-button').click();
    await expect(page.getByTestId('play-button')).toBeEnabled();

    await page.getByTestId('play-button').click();
    await page.waitForTimeout(1200);

    const samples: number[] = [];
    for (let i = 0; i < 6; i += 1) {
      const value = Number(await page.getByTestId('video-time-ms').innerText());
      samples.push(value);
      await page.waitForTimeout(250);
    }

    expect(samples.length).toBeGreaterThan(4);
    expect(samples[samples.length - 1]).toBeGreaterThan(samples[0]);
    for (let i = 1; i < samples.length; i += 1) {
      expect(samples[i]).toBeGreaterThanOrEqual(samples[i - 1]);
    }
  });

  test('default flow is passive-first then survey', async ({ page }) => {
    await installMediaMocks(page);

    await page.goto('/study/demo');
    await page.getByTestId('agree-button').click();
    await page.getByTestId('audio-confirmed-checkbox').check();
    await page.getByTestId('start-watch-button').click();

    await expect(page.getByTestId('watch-stage')).toBeVisible();
    await expect(page.getByTestId('continuous-dial-panel')).toHaveCount(0);
    await expect(page.getByRole('button', { name: /like/i })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /dislike/i })).toHaveCount(0);

    await page.evaluate(() => {
      const video = document.querySelector('[data-testid=\"study-video\"]') as HTMLVideoElement | null;
      if (!video) {
        return;
      }
      video.currentTime = 1.2;
      video.dispatchEvent(new Event('ended'));
    });

    await expect(page.getByTestId('survey-stage')).toBeVisible();
    await expect(page.getByTestId('annotation-stage')).toHaveCount(0);
    await expect
      .poll(async () => {
        return page.evaluate(() => {
          const webcam = document.querySelector('[data-testid=\"webcam-preview\"]') as HTMLVideoElement | null;
          return webcam?.srcObject === null;
        });
      })
      .toBe(true);
    await expect(page.getByTestId('survey-overall-engagement-input')).toBeVisible();
    await expect(page.getByTestId('survey-overall-engagement-input')).toHaveAttribute('type', 'number');
    await expect(page.getByTestId('survey-content-clarity-input')).toBeVisible();
    await expect(page.getByTestId('survey-content-clarity-input')).toHaveAttribute('type', 'number');
    await expect(page.getByTestId('survey-additional-comments-input')).toBeVisible();
  });

  test('complete playback uploads survey rows with annotation skipped', async ({ page }) => {
    await installMediaMocks(page);

    let uploadPayload: UploadPayload | null = null;
    await page.route('**/api/upload', async (route) => {
      const body = route.request().postDataJSON() as UploadPayload;
      uploadPayload = body;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          sessionId: 'test-session-complete',
          acceptedAt: new Date().toISOString(),
          events: body.eventTimeline.length,
          dialSamples: 0,
          annotations: body.annotations.length,
          annotationSkipped: body.annotationSkipped,
          surveyResponses: body.surveyResponses.length,
          frames: 0,
          framePointers: 1
        })
      });
    });

    await page.goto('/study/demo');
    await page.getByTestId('agree-button').click();
    await page.getByTestId('audio-confirmed-checkbox').check();
    await page.getByTestId('start-watch-button').click();
    await expect(page.getByTestId('watch-stage')).toBeVisible();

    await page.evaluate(() => {
      const video = document.querySelector('[data-testid=\"study-video\"]') as HTMLVideoElement | null;
      if (!video) {
        return;
      }
      video.currentTime = 2.5;
      video.dispatchEvent(new Event('timeupdate'));
      video.dispatchEvent(new Event('ended'));
    });

    await expect(page.getByTestId('survey-stage')).toBeVisible();
    await page.getByTestId('survey-overall-engagement-input').fill('4');
    await page.getByTestId('survey-content-clarity-input').fill('3');
    await page
      .getByTestId('survey-additional-comments-input')
      .fill('At 0:18 I felt strong curiosity and engagement.');
    await page.getByTestId('finish-button').click();

    await expect(page.getByTestId('upload-status')).toContainText('Upload complete');
    expect(uploadPayload).not.toBeNull();

    expect(uploadPayload!.annotationSkipped).toBe(true);
    expect(uploadPayload!.annotations).toHaveLength(0);

    const surveyKeys = new Set(uploadPayload!.surveyResponses.map((entry) => entry.questionKey));
    expect(surveyKeys.has('annotation_status')).toBe(true);
    expect(surveyKeys.has('session_completion_status')).toBe(true);
    expect(surveyKeys.has('overall_interest_likert')).toBe(true);
    expect(surveyKeys.has('recall_comprehension_likert')).toBe(true);
    expect(surveyKeys.has('survey_score_inputs')).toBe(true);
    expect(surveyKeys.has('post_annotation_comment')).toBe(true);
    expect(uploadPayload!.traceRows.length).toBeGreaterThan(0);
    expect(uploadPayload!.traceRows.every((row) => Number.isFinite(row.video_time_ms))).toBe(true);
    expect(uploadPayload!.traceRows.some((row) => typeof row.quality_score === 'number')).toBe(true);
    expect(uploadPayload!.traceRows.some((row) => typeof row.tracking_confidence === 'number')).toBe(true);
  });

  test('telemetry events include required types and align to video_time_ms', async ({ page }) => {
    await installMediaMocks(page);

    let uploadPayload: UploadPayload | null = null;
    await page.route('**/api/upload', async (route) => {
      const body = route.request().postDataJSON() as UploadPayload;
      uploadPayload = body;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ok: true,
          sessionId: 'test-session-id',
          acceptedAt: new Date().toISOString(),
          events: body.eventTimeline.length,
          dialSamples: 0,
          annotations: 0,
          annotationSkipped: true,
          surveyResponses: 1,
          frames: 0,
          framePointers: 1
        })
      });
    });

    await page.goto('/study/demo');
    await page.getByTestId('agree-button').click();
    await page.getByTestId('audio-confirmed-checkbox').check();
    await page.getByTestId('start-watch-button').click();
    await page.getByTestId('play-button').click();
    await page.waitForTimeout(250);
    await page.getByTestId('pause-button').click();

    await page.evaluate(() => {
      const video = document.querySelector('[data-testid=\"study-video\"]') as HTMLVideoElement | null;
      if (!video) {
        return;
      }
      video.dispatchEvent(new Event('seeking'));
      video.currentTime = 4.0;
      video.dispatchEvent(new Event('seeked'));
      video.dispatchEvent(new Event('seeking'));
      video.currentTime = 1.0;
      video.dispatchEvent(new Event('seeked'));
      video.muted = true;
      video.dispatchEvent(new Event('volumechange'));
      video.muted = false;
      video.dispatchEvent(new Event('volumechange'));

      const scopedWindow = window as Window & {
        __mockFullscreenElement?: Element | null;
        __mockVisibilityState?: DocumentVisibilityState;
      };
      scopedWindow.__mockFullscreenElement = document.body;
      document.dispatchEvent(new Event('fullscreenchange'));
      scopedWindow.__mockFullscreenElement = null;
      document.dispatchEvent(new Event('fullscreenchange'));

      scopedWindow.__mockVisibilityState = 'hidden';
      document.dispatchEvent(new Event('visibilitychange'));
      scopedWindow.__mockVisibilityState = 'visible';
      document.dispatchEvent(new Event('visibilitychange'));

      window.dispatchEvent(new Event('blur'));
      window.dispatchEvent(new Event('focus'));
    });

    await page.getByTestId('end-early-button').click();
    await expect(page.getByTestId('upload-status')).toContainText('Upload complete');
    expect(uploadPayload).not.toBeNull();

    const timeline = uploadPayload!.eventTimeline;
    const requiredTypes = new Set([
      'play',
      'pause',
      'seek_start',
      'seek_end',
      'rewind',
      'mute',
      'unmute',
      'volume_change',
      'fullscreen_enter',
      'fullscreen_exit',
      'visibility_hidden',
      'visibility_visible',
      'window_blur',
      'window_focus',
      'abandonment'
    ]);
    const observedTypes = new Set(timeline.map((event) => event.type));

    requiredTypes.forEach((type) => {
      expect(observedTypes.has(type)).toBe(true);
    });

    timeline.forEach((event) => {
      expect(typeof event.sessionId).toBe('string');
      expect(typeof event.videoId).toBe('string');
      expect(Number.isInteger(event.videoTimeMs)).toBe(true);
      expect(event.videoTimeMs).toBeGreaterThanOrEqual(0);
      expect(Number.isInteger(event.clientMonotonicMs)).toBe(true);
      expect(Number.isInteger(event.wallTimeMs)).toBe(true);
    });

    const seekEndEvents = timeline.filter((event) => event.type === 'seek_end');
    expect(seekEndEvents.length).toBeGreaterThan(0);
    seekEndEvents.forEach((event) => {
      const toVideoTimeMs = Number(event.details?.toVideoTimeMs);
      expect(Number.isFinite(toVideoTimeMs)).toBe(true);
      expect(Math.abs(event.videoTimeMs - toVideoTimeMs)).toBeLessThanOrEqual(50);
    });

    const abandonmentEvent = timeline.find((event) => event.type === 'abandonment');
    expect(abandonmentEvent).toBeDefined();
    expect(Number(abandonmentEvent?.details?.lastVideoTimeMs)).toBeGreaterThanOrEqual(0);
  });
});
