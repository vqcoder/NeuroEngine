import { useCallback, useMemo, useRef, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import type { PredictorTimelinePoint } from '../utils/predictorTimeline';
import {
  buildScenesFromTrace,
  simulateReorder,
  formatDelta,
  getEngagementColour,
  type SceneSegment,
  type SimulationResult,
} from '../utils/editSimulator';

// ── Colour map ─────────────────────────────────────────────────────────────

const COLOUR_MAP: Record<'green' | 'amber' | 'red', string> = {
  green: '#22c55e',
  amber: '#f59e0b',
  red: '#ef4444',
};

// ── Props ──────────────────────────────────────────────────────────────────

type EditSimulatorProps = {
  trace: PredictorTimelinePoint[];
};

// ── Component ──────────────────────────────────────────────────────────────

export default function EditSimulator({ trace }: EditSimulatorProps) {
  const [splitPoints, setSplitPoints] = useState<number[]>([]);
  const [newSplitInput, setNewSplitInput] = useState('');
  const [simulationResult, setSimulationResult] = useState<SimulationResult | null>(null);
  const [orderedIds, setOrderedIds] = useState<string[]>([]);
  const dragItemRef = useRef<number | null>(null);

  const scenes = useMemo(
    () => buildScenesFromTrace(trace, splitPoints),
    [trace, splitPoints],
  );

  // Keep orderedIds in sync when scenes change.
  useMemo(() => {
    setOrderedIds(scenes.map((s) => s.id));
    setSimulationResult(null);
  }, [scenes]);

  const orderedScenes = useMemo(() => {
    const map = new Map(scenes.map((s) => [s.id, s]));
    return orderedIds.map((id) => map.get(id)).filter((s): s is SceneSegment => !!s);
  }, [scenes, orderedIds]);

  // ── Split point management ─────────────────────────────────────────────

  const addSplit = useCallback(() => {
    const value = parseFloat(newSplitInput);
    if (Number.isFinite(value) && value > 0 && !splitPoints.includes(value)) {
      setSplitPoints((prev) => [...prev, value].sort((a, b) => a - b));
    }
    setNewSplitInput('');
  }, [newSplitInput, splitPoints]);

  const removeSplit = useCallback((sec: number) => {
    setSplitPoints((prev) => prev.filter((s) => s !== sec));
  }, []);

  // ── Drag and drop ──────────────────────────────────────────────────────

  const handleDragStart = (index: number) => {
    dragItemRef.current = index;
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (dragItemRef.current === null || dragItemRef.current === index) return;
    setOrderedIds((prev) => {
      const next = [...prev];
      const [moved] = next.splice(dragItemRef.current!, 1);
      next.splice(index, 0, moved);
      dragItemRef.current = index;
      return next;
    });
  };

  const handleDragEnd = () => {
    dragItemRef.current = null;
  };

  // ── Simulate ───────────────────────────────────────────────────────────

  const runSimulation = () => {
    const result = simulateReorder(scenes, orderedIds);
    setSimulationResult(result);
  };

  // ── Chart data ─────────────────────────────────────────────────────────

  const originalChartData = useMemo(
    () =>
      simulationResult?.originalTrace.map((v, i) => ({ idx: i, value: v })) ?? [],
    [simulationResult],
  );

  const simulatedChartData = useMemo(
    () =>
      simulationResult?.simulatedTrace.map((v, i) => ({ idx: i, value: v })) ?? [],
    [simulationResult],
  );

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <Stack spacing={3}>
      {/* 1. Split point editor */}
      <Box>
        <Typography variant="subtitle1" fontWeight={700}>
          Define Scenes
        </Typography>
        <Typography variant="body2" color="text.secondary" mb={1}>
          Add cut points (in seconds) to split the video into scenes
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <TextField
            size="small"
            type="number"
            placeholder="Seconds"
            value={newSplitInput}
            onChange={(e) => setNewSplitInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addSplit(); }}
            sx={{ width: 120 }}
          />
          <Button size="small" variant="outlined" onClick={addSplit}>
            Add Cut
          </Button>
        </Stack>
        {splitPoints.length > 0 && (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap mt={1}>
            {splitPoints.map((sec) => (
              <Chip
                key={sec}
                label={`${sec}s`}
                size="small"
                onDelete={() => removeSplit(sec)}
              />
            ))}
          </Stack>
        )}
      </Box>

      {/* 2. Scene strip */}
      {scenes.length >= 2 && (
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            Drag to Reorder
          </Typography>
          <Typography variant="body2" color="text.secondary" mb={1}>
            Drag scenes into a new order, then click Run Simulation
          </Typography>
          <Stack
            direction="row"
            spacing={1}
            sx={{ overflowX: 'auto', pb: 1 }}
          >
            {orderedScenes.map((scene, index) => {
              const colour = COLOUR_MAP[getEngagementColour(scene.avgAttention)];
              const duration = Math.round(scene.endSec - scene.startSec);
              return (
                <Box
                  key={scene.id}
                  draggable
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDragEnd={handleDragEnd}
                  sx={{
                    minWidth: 130,
                    p: 1.5,
                    borderLeft: `4px solid ${colour}`,
                    borderRadius: 1,
                    bgcolor: 'background.paper',
                    cursor: 'grab',
                    '&:active': { cursor: 'grabbing' },
                    userSelect: 'none',
                  }}
                >
                  <Typography variant="body2" fontWeight={600}>
                    {scene.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {duration}s &middot; att {scene.avgAttention}
                  </Typography>
                </Box>
              );
            })}
          </Stack>
        </Box>
      )}

      {/* 3. Simulate button */}
      <Button
        variant="contained"
        disabled={scenes.length < 2}
        onClick={runSimulation}
        sx={{ alignSelf: 'flex-start' }}
      >
        Run Simulation
      </Button>

      {/* 4. Simulation result */}
      {simulationResult && (
        <Box>
          <Typography
            variant="h4"
            fontWeight={700}
            sx={{
              color: simulationResult.deltaPercent > 0
                ? '#22c55e'
                : simulationResult.deltaPercent < 0
                  ? '#ef4444'
                  : 'text.primary',
              mb: 2,
              fontFamily: 'monospace',
            }}
          >
            {formatDelta(simulationResult.deltaPercent)}
          </Typography>

          <Stack direction="row" spacing={2}>
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Original
              </Typography>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={originalChartData}>
                  <XAxis dataKey="idx" hide />
                  <YAxis domain={[0, 100]} hide />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#94a3b8"
                    dot={false}
                    strokeWidth={1.5}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
            <Box sx={{ flex: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Simulated
              </Typography>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={simulatedChartData}>
                  <XAxis dataKey="idx" hide />
                  <YAxis domain={[0, 100]} hide />
                  <Tooltip />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke={simulationResult.deltaPercent >= 0 ? '#22c55e' : '#ef4444'}
                    dot={false}
                    strokeWidth={1.5}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </Stack>
        </Box>
      )}
    </Stack>
  );
}
