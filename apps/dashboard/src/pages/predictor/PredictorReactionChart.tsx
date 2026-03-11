import {
  Box,
  FormControlLabel,
  FormGroup,
  Stack,
  Switch,
  Typography
} from '@mui/material';
import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import type {
  PredictorChartClickState,
  PredictorLayerVisibility,
  PredictorTimelinePoint
} from '../../utils/predictorTimeline';
import { toSeekableSecond } from '../../utils/predictorTimeline';

export type PredictorReactionChartProps = {
  timeline: PredictorTimelinePoint[];
  layerVisibility: PredictorLayerVisibility;
  currentSec: number;
  onToggleLayer: (key: keyof PredictorLayerVisibility) => void;
  onChartClick: (state: PredictorChartClickState) => void;
};

export default function PredictorReactionChart({
  timeline,
  layerVisibility,
  currentSec,
  onToggleLayer,
  onChartClick
}: PredictorReactionChartProps) {
  return (
    <Stack spacing={1.5}>
      <Typography variant="h6" fontWeight={700}>
        Predicted reaction timeline
      </Typography>

      <FormGroup row sx={{ columnGap: 2 }}>
        <FormControlLabel
          control={<Switch checked={layerVisibility.attentionScore} onChange={() => onToggleLayer('attentionScore')} />}
          label="attention_score"
        />
        <FormControlLabel
          control={<Switch checked={layerVisibility.rewardProxy} onChange={() => onToggleLayer('rewardProxy')} />}
          label="reward_proxy"
        />
        <FormControlLabel
          control={<Switch checked={layerVisibility.dial} onChange={() => onToggleLayer('dial')} />}
          label="dial"
        />
        <FormControlLabel
          control={<Switch checked={layerVisibility.valenceProxy} onChange={() => onToggleLayer('valenceProxy')} />}
          label="valence_proxy"
        />
        <FormControlLabel
          control={<Switch checked={layerVisibility.arousalProxy} onChange={() => onToggleLayer('arousalProxy')} />}
          label="arousal_proxy"
        />
        <FormControlLabel
          control={<Switch checked={layerVisibility.noveltyProxy} onChange={() => onToggleLayer('noveltyProxy')} />}
          label="novelty_proxy"
        />
        <FormControlLabel
          control={
            <Switch
              checked={layerVisibility.attentionVelocity}
              onChange={() => onToggleLayer('attentionVelocity')}
            />
          }
          label="attention_velocity"
        />
        <FormControlLabel
          control={
            <Switch
              checked={layerVisibility.blinkInhibition}
              onChange={() => onToggleLayer('blinkInhibition')}
            />
          }
          label="blink_inhibition"
        />
        <FormControlLabel
          control={<Switch checked={layerVisibility.blinkRate} onChange={() => onToggleLayer('blinkRate')} />}
          label="blink_rate"
        />
        <FormControlLabel
          control={
            <Switch
              checked={layerVisibility.trackingConfidence}
              onChange={() => onToggleLayer('trackingConfidence')}
            />
          }
          label="tracking_confidence"
        />
      </FormGroup>

      <Box sx={{ width: '100%', height: 460 }} data-testid="predictor-chart">
        <ResponsiveContainer>
          <ComposedChart
            data={timeline}
            margin={{ top: 8, right: 24, left: 8, bottom: 8 }}
            onClick={(state) => onChartClick(state as PredictorChartClickState)}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,151,168,0.18)" />
            <XAxis dataKey="tSec" tickFormatter={(value) => `${value}s`} tick={{ fill: '#8a8895' }} axisLine={{ stroke: '#26262f' }} tickLine={{ stroke: '#26262f' }} />
            <YAxis yAxisId="reaction" domain={[0, 100]} width={56} tick={{ fill: '#8a8895' }} axisLine={{ stroke: '#26262f' }} tickLine={{ stroke: '#26262f' }} />
            <YAxis yAxisId="behavior" orientation="right" domain={[-1, 1]} width={56} tick={{ fill: '#8a8895' }} axisLine={{ stroke: '#26262f' }} tickLine={{ stroke: '#26262f' }} />
            <Tooltip
              contentStyle={{ background: '#141419', border: '1px solid #26262f', borderRadius: 8 }}
              labelStyle={{ color: '#c8f031', fontWeight: 700, marginBottom: 4 }}
              itemStyle={{ color: '#e8e6e3', fontSize: 12 }}
              labelFormatter={(value) => `t = ${value}s`}
              cursor={{ stroke: '#c8f031', strokeWidth: 1, strokeDasharray: '4 3' }}
            />
            <Legend wrapperStyle={{ color: '#8a8895', fontSize: 12 }} />
            <ReferenceLine
              x={toSeekableSecond(currentSec)}
              yAxisId="reaction"
              stroke="#00e5ff"
              strokeDasharray="5 3"
              ifOverflow="extendDomain"
            />

            {layerVisibility.attentionScore ? (
              <Line yAxisId="reaction" type="monotone" dataKey="attentionScore" stroke="#2f7dff" dot={false} />
            ) : null}
            {layerVisibility.rewardProxy ? (
              <Line yAxisId="reaction" type="monotone" dataKey="rewardProxy" stroke="#ff8f3d" dot={false} />
            ) : null}
            {layerVisibility.dial ? (
              <Line yAxisId="reaction" type="monotone" dataKey="dial" stroke="#6d597a" dot={false} />
            ) : null}
            {layerVisibility.valenceProxy ? (
              <Line yAxisId="reaction" type="monotone" dataKey="valenceProxy" stroke="#457b9d" dot={false} />
            ) : null}
            {layerVisibility.arousalProxy ? (
              <Line yAxisId="reaction" type="monotone" dataKey="arousalProxy" stroke="#ef476f" dot={false} />
            ) : null}
            {layerVisibility.noveltyProxy ? (
              <Line yAxisId="reaction" type="monotone" dataKey="noveltyProxy" stroke="#f4a261" dot={false} />
            ) : null}
            {layerVisibility.trackingConfidence ? (
              <Line yAxisId="reaction" type="monotone" dataKey="trackingConfidence" stroke="#aaaaaa" strokeDasharray="6 3" dot={false} />
            ) : null}
            {layerVisibility.attentionVelocity ? (
              <Line
                yAxisId="behavior"
                type="monotone"
                dataKey="attentionVelocity"
                stroke="#e63946"
                strokeDasharray="4 3"
                dot={false}
              />
            ) : null}
            {layerVisibility.blinkInhibition ? (
              <Line yAxisId="behavior" type="monotone" dataKey="blinkInhibition" stroke="#8d99ae" dot={false} />
            ) : null}
            {layerVisibility.blinkRate ? (
              <Line
                yAxisId="behavior"
                type="monotone"
                dataKey="blinkRate"
                stroke="#fb8500"
                strokeDasharray="2 3"
                dot={false}
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </Box>
    </Stack>
  );
}
