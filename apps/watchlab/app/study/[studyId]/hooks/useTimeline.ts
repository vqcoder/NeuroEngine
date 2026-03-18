/**
 * useTimeline — Timeline event tracking, annotation markers, and dial sampling
 * extracted from StudyClient.
 *
 * Owns:
 *   State:  timeline, annotationMarkers, annotationSkipped
 *   Refs:   timelineRef, annotationMarkersRef, dialSamplesRef
 *   Fns:    appendEvent, appendAbandonmentEvent, addAnnotationMarker, removeAnnotationMarker
 */

import { useEffect, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import {
  type AnnotationMarker,
  type DialSample,
  type TimelineEvent,
} from '@/lib/schema';
import { VideoTimeTracker } from '@/lib/videoClock';
import {
  type MarkerType,
  type StudyStage,
  markerLabels,
} from '@/lib/studyTypes';
import { safeUuid } from '@/lib/studyHelpers';

// ── Types ──────────────────────────────────────────────────────────────────

export interface UseTimelineDeps {
  studyId: string;
  sessionId: string;
  videoId: string;
  videoTimeTrackerRef: MutableRefObject<VideoTimeTracker>;
  studyVideoRef: MutableRefObject<HTMLVideoElement | null>;
  monotonicClientTimeRef: MutableRefObject<number>;
  lastObservedVideoTimeRef: MutableRefObject<number>;
  stageRef: MutableRefObject<StudyStage>;
}

export interface UseTimelineReturn {
  // State
  timeline: TimelineEvent[];
  annotationMarkers: AnnotationMarker[];
  annotationSkipped: boolean;

  // Refs
  timelineRef: MutableRefObject<TimelineEvent[]>;
  annotationMarkersRef: MutableRefObject<AnnotationMarker[]>;
  annotationSkippedRef: MutableRefObject<boolean>;
  dialSamplesRef: MutableRefObject<DialSample[]>;

  // Functions
  appendEvent: (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward?: boolean,
    explicitVideoTimeMs?: number,
  ) => TimelineEvent;
  appendAbandonmentEvent: (
    reason: string,
    sourceStage: StudyStage,
    explicitVideoTimeMs?: number,
  ) => number;
  addAnnotationMarker: (markerType: MarkerType, noteDraft: string, getCurrentAnnotationTimeMs: () => number) => void;
  removeAnnotationMarker: (markerId: string) => void;
  createTimelineEvent: (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward?: boolean,
    explicitVideoTimeMs?: number,
  ) => TimelineEvent;
  sampleSyncedVideoTimeMs: (allowBackward?: boolean) => number;

  // Setters
  setTimeline: React.Dispatch<React.SetStateAction<TimelineEvent[]>>;
  setAnnotationMarkers: React.Dispatch<React.SetStateAction<AnnotationMarker[]>>;
  setAnnotationSkipped: React.Dispatch<React.SetStateAction<boolean>>;
  setVideoTimeMs: React.Dispatch<React.SetStateAction<number>>;

  // Derived state
  videoTimeMs: number;
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useTimeline(deps: UseTimelineDeps): UseTimelineReturn {
  const {
    studyId, sessionId, videoId,
    videoTimeTrackerRef, studyVideoRef,
    monotonicClientTimeRef, lastObservedVideoTimeRef,
    stageRef,
  } = deps;

  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [videoTimeMs, setVideoTimeMs] = useState(0);
  const [annotationMarkers, setAnnotationMarkers] = useState<AnnotationMarker[]>([]);
  const [annotationSkipped, setAnnotationSkipped] = useState(false);

  const timelineRef = useRef<TimelineEvent[]>([]);
  const annotationMarkersRef = useRef<AnnotationMarker[]>([]);
  const annotationSkippedRef = useRef(false);
  const dialSamplesRef = useRef<DialSample[]>([]);

  // Keep refs in sync with state
  useEffect(() => {
    annotationMarkersRef.current = annotationMarkers;
  }, [annotationMarkers]);

  useEffect(() => {
    annotationSkippedRef.current = annotationSkipped;
  }, [annotationSkipped]);

  // ── Helpers ────────────────────────────────────────────────────────────

  const nextMonotonicClientMs = () => {
    const candidate = Math.max(0, Math.round(performance.now()));
    const nextValue =
      candidate > monotonicClientTimeRef.current
        ? candidate
        : monotonicClientTimeRef.current + 1;
    monotonicClientTimeRef.current = nextValue;
    return nextValue;
  };

  const sampleSyncedVideoTimeMs = (allowBackward = false) => {
    const video = studyVideoRef.current;
    const measuredMs = video
      ? Math.round(video.currentTime * 1000)
      : videoTimeTrackerRef.current.getVideoTimeMs();
    const nextMs = videoTimeTrackerRef.current.sample({
      measuredVideoTimeMs: measuredMs,
      clientMonotonicMs: performance.now(),
      allowBackward,
      isPlaying: Boolean(video && !video.paused && !video.ended),
      playbackRate: video?.playbackRate ?? 1,
      isBuffering: Boolean(video && !video.paused && !video.ended && video.readyState < 3),
    });
    setVideoTimeMs(nextMs);
    return nextMs;
  };

  const createTimelineEvent = (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward = false,
    explicitVideoTimeMs?: number,
  ): TimelineEvent => {
    const resolvedVideoTimeMs =
      typeof explicitVideoTimeMs === 'number'
        ? explicitVideoTimeMs
        : sampleSyncedVideoTimeMs(allowBackward);

    return {
      type,
      sessionId,
      videoId: videoId || `video-${studyId}`,
      wallTimeMs: Date.now(),
      clientMonotonicMs: nextMonotonicClientMs(),
      videoTimeMs: resolvedVideoTimeMs,
      details,
    };
  };

  const appendEvent = (
    type: TimelineEvent['type'],
    details?: TimelineEvent['details'],
    allowBackward = false,
    explicitVideoTimeMs?: number,
  ) => {
    const event = createTimelineEvent(type, details, allowBackward, explicitVideoTimeMs);
    timelineRef.current = [...timelineRef.current, event];
    setTimeline(timelineRef.current);
    return event;
  };

  const appendAbandonmentEvent = (
    reason: string,
    sourceStage: StudyStage,
    explicitVideoTimeMs?: number,
  ) => {
    const measuredVideoTimeMs = sampleSyncedVideoTimeMs(true);
    const lastVideoTimeMs =
      typeof explicitVideoTimeMs === 'number'
        ? explicitVideoTimeMs
        : Math.max(lastObservedVideoTimeRef.current, measuredVideoTimeMs);

    const details = { reason, sourceStage, lastVideoTimeMs };
    appendEvent('abandonment', details, true, lastVideoTimeMs);
    appendEvent('session_incomplete', details, true, lastVideoTimeMs);
    return lastVideoTimeMs;
  };

  // ── Annotation markers ────────────────────────────────────────────────

  const addAnnotationMarker = (
    markerType: MarkerType,
    noteDraft: string,
    getCurrentAnnotationTimeMs: () => number,
  ) => {
    const videoTimeForMarker = getCurrentAnnotationTimeMs();
    const note = noteDraft.trim();
    const marker: AnnotationMarker = {
      id: safeUuid(),
      sessionId,
      videoId: videoId || `video-${studyId}`,
      markerType,
      videoTimeMs: videoTimeForMarker,
      note: note.length > 0 ? note : null,
      createdAt: new Date().toISOString(),
    };

    setAnnotationMarkers((prev) => [...prev, marker]);
    setAnnotationSkipped(false);

    appendEvent(
      'annotation_tag_set',
      {
        markerType,
        markerLabel: markerLabels[markerType],
        videoTimeMs: videoTimeForMarker,
        hasNote: Boolean(marker.note),
      },
      true,
      videoTimeForMarker,
    );
  };

  const removeAnnotationMarker = (markerId: string) => {
    const marker = annotationMarkersRef.current.find((entry) => entry.id === markerId);
    setAnnotationMarkers((prev) => prev.filter((entry) => entry.id !== markerId));
    if (marker) {
      appendEvent(
        'annotation_tag_set',
        {
          action: 'removed',
          markerType: marker.markerType,
          videoTimeMs: marker.videoTimeMs,
        },
        true,
        marker.videoTimeMs,
      );
    }
  };

  return {
    timeline, annotationMarkers, annotationSkipped,
    timelineRef, annotationMarkersRef, annotationSkippedRef, dialSamplesRef,
    appendEvent, appendAbandonmentEvent,
    addAnnotationMarker, removeAnnotationMarker,
    createTimelineEvent, sampleSyncedVideoTimeMs,
    setTimeline, setAnnotationMarkers, setAnnotationSkipped, setVideoTimeMs,
    videoTimeMs,
  };
}
