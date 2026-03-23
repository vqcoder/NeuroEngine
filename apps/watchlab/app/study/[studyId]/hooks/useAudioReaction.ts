/**
 * useAudioReaction — Mic consent, energy sampling, and reaction detection.
 *
 * Detects laugh/gasp/sharp-inhale/exclamation moments via mic RMS energy.
 * No raw audio is stored — only energy envelope and reaction classification.
 */

import { useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import type { TimelineEvent } from '@/lib/schema';

// ── Constants ──────────────────────────────────────────────────────────────

const SAMPLE_RATE_MS = 100;
const ENERGY_THRESHOLD = 0.15;
const SUSTAINED_MS = 150;
const COOLDOWN_MS = 1000;
const FFT_SIZE = 256;

// ── Types ──────────────────────────────────────────────────────────────────

export type MicStatus = 'idle' | 'requesting' | 'granted' | 'denied' | 'bypassed';

export type ReactionType = 'laugh' | 'gasp' | 'sharp_inhale' | 'exclamation';

type AppendEventFn = (
  type: TimelineEvent['type'],
  details?: TimelineEvent['details'],
  allowBackward?: boolean,
  explicitVideoTimeMs?: number,
) => void;

export interface UseAudioReactionReturn {
  micStatus: MicStatus;
  micEnergyLevel: number;
  audioReactionCount: number;
  startMicCapture: (appendEvent: AppendEventFn) => Promise<void>;
  stopMicCapture: () => void;
  pauseEnergyMonitoring: () => void;
  resumeEnergyMonitoring: (appendEvent: AppendEventFn) => void;
  bypassMic: (appendEvent: AppendEventFn) => void;
  micStreamRef: MutableRefObject<MediaStream | null>;
}

// ── Helpers (exported for testing) ─────────────────────────────────────────

export function computeRmsEnergy(samples: Uint8Array): number {
  if (samples.length === 0) return 0;
  let sumSq = 0;
  for (let i = 0; i < samples.length; i++) {
    // Uint8 time-domain data is centred at 128; normalise to [-1, 1]
    const norm = (samples[i] - 128) / 128;
    sumSq += norm * norm;
  }
  return Math.sqrt(sumSq / samples.length);
}

export function classifyReaction(energy: number, durationMs: number): ReactionType {
  if (energy > 0.7) return 'exclamation';
  if (energy > 0.5) return 'gasp';
  if (energy > 0.3 && durationMs > 300) return 'laugh';
  return 'sharp_inhale';
}

// ── Hook ───────────────────────────────────────────────────────────────────

export function useAudioReaction(): UseAudioReactionReturn {
  const [micStatus, setMicStatus] = useState<MicStatus>('idle');
  const [micEnergyLevel, setMicEnergyLevel] = useState(0);
  const [audioReactionCount, setAudioReactionCount] = useState(0);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const detectionTimerRef = useRef<number | null>(null);
  const lastReactionMsRef = useRef(0);
  const sustainedStartMsRef = useRef<number | null>(null);

  const stopMicCapture = () => {
    if (detectionTimerRef.current !== null) {
      window.clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => undefined);
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    setMicEnergyLevel(0);
  };

  const startMicCapture = async (appendEvent: AppendEventFn) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicStatus('denied');
      appendEvent('mic_denied', { reason: 'unsupported' });
      return;
    }

    setMicStatus('requesting');

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });

      micStreamRef.current = stream;

      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) {
        setMicStatus('denied');
        appendEvent('mic_denied', { reason: 'no_audio_context' });
        return;
      }

      const ctx = new AudioCtx();
      audioContextRef.current = ctx;

      const analyser = ctx.createAnalyser();
      analyser.fftSize = FFT_SIZE;
      analyserRef.current = analyser;

      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyser);

      setMicStatus('granted');
      appendEvent('mic_granted');

      const dataArray = new Uint8Array(analyser.fftSize);

      detectionTimerRef.current = window.setInterval(() => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteTimeDomainData(dataArray);

        const energy = computeRmsEnergy(dataArray);
        setMicEnergyLevel(energy);
        const now = performance.now();

        if (energy > ENERGY_THRESHOLD) {
          if (sustainedStartMsRef.current === null) {
            sustainedStartMsRef.current = now;
          }
          const sustainedDuration = now - sustainedStartMsRef.current;

          if (
            sustainedDuration >= SUSTAINED_MS &&
            now - lastReactionMsRef.current > COOLDOWN_MS
          ) {
            const reactionType = classifyReaction(energy, sustainedDuration);
            appendEvent('audio_reaction', {
              reaction_type: reactionType,
              energy: Math.round(energy * 1000) / 1000,
              confidence: Math.round(energy * 1000) / 1000,
              duration_ms: Math.round(sustainedDuration),
            });
            setAudioReactionCount((c) => c + 1);
            lastReactionMsRef.current = now;
            sustainedStartMsRef.current = null;
          }
        } else {
          sustainedStartMsRef.current = null;
        }
      }, SAMPLE_RATE_MS);
    } catch (error) {
      setMicStatus('denied');
      appendEvent('mic_denied', {
        reason: error instanceof Error ? error.message : 'unknown',
      });
    }
  };

  const pauseEnergyMonitoring = () => {
    if (detectionTimerRef.current !== null) {
      window.clearInterval(detectionTimerRef.current);
      detectionTimerRef.current = null;
    }
  };

  const resumeEnergyMonitoring = (appendEvent: AppendEventFn) => {
    if (detectionTimerRef.current !== null) return; // already running
    if (!analyserRef.current) return;

    const dataArray = new Uint8Array(analyserRef.current.fftSize);

    detectionTimerRef.current = window.setInterval(() => {
      if (!analyserRef.current) return;
      analyserRef.current.getByteTimeDomainData(dataArray);

      const energy = computeRmsEnergy(dataArray);
      setMicEnergyLevel(energy);
      const now = performance.now();

      if (energy > ENERGY_THRESHOLD) {
        if (sustainedStartMsRef.current === null) {
          sustainedStartMsRef.current = now;
        }
        const sustainedDuration = now - sustainedStartMsRef.current;

        if (
          sustainedDuration >= SUSTAINED_MS &&
          now - lastReactionMsRef.current > COOLDOWN_MS
        ) {
          const reactionType = classifyReaction(energy, sustainedDuration);
          appendEvent('audio_reaction', {
            reaction_type: reactionType,
            energy: Math.round(energy * 1000) / 1000,
            confidence: Math.round(energy * 1000) / 1000,
            duration_ms: Math.round(sustainedDuration),
          });
          setAudioReactionCount((c) => c + 1);
          lastReactionMsRef.current = now;
          sustainedStartMsRef.current = null;
        }
      } else {
        sustainedStartMsRef.current = null;
      }
    }, SAMPLE_RATE_MS);
  };

  const bypassMic = (appendEvent: AppendEventFn) => {
    setMicStatus('bypassed');
    appendEvent('mic_bypassed', {});
  };

  return {
    micStatus,
    micEnergyLevel,
    audioReactionCount,
    startMicCapture,
    stopMicCapture,
    pauseEnergyMonitoring,
    resumeEnergyMonitoring,
    bypassMic,
    micStreamRef,
  };
}
