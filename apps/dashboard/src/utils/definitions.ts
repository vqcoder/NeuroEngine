/**
 * In-context definitions for all terms used in the readout dashboard.
 * Used by TermTooltip to surface contextual help on hover.
 */

export interface TermDefinition {
  label: string;
  description: string;
  formula?: string;
}

export const DEFINITIONS: Record<string, TermDefinition> = {

  // ─── Data Modules ───────────────────────────────────────────────────────────

  context: {
    label: 'Context',
    description: 'Structural metadata about the video: scenes, cuts, and CTA markers. Provides the timeline skeleton that all signal layers are anchored to.',
  },
  traces: {
    label: 'Traces',
    description: 'Time-series signal lines (attention, blink rate, reward proxy, AU channels, etc.) aligned to video_time_ms. These are passive biometric proxies — not direct measurements.',
  },
  segments: {
    label: 'Segments',
    description: 'Detected windows of sustained signal behavior: golden scenes, dead zones, attention gains/losses, and confusion segments. Each has a start/end time, magnitude, and confidence.',
  },
  diagnostics: {
    label: 'Diagnostics',
    description: 'Scene-level cards surfacing specific signal events: hook strength, golden scene, CTA receptivity, attention drop, confusion, and recovery. Each card points to a timestamped window in the video.',
  },
  labels: {
    label: 'Labels',
    description: 'Explicit post-view annotations (engaging, confusing, stop-watching, CTA-landed moments) and survey responses (interest, recall, action intent). These are participant-reported, not inferred.',
  },
  quality: {
    label: 'Quality',
    description: 'Session signal quality: face detection rate, tracking confidence, usable seconds, and low-confidence windows. Low quality reduces reliability of trace-derived scores.',
  },
  aggregate_metrics: {
    label: 'Aggregate Metrics',
    description: 'Cross-viewer computed diagnostics — only available in aggregate view. Includes attentional synchrony, narrative control, reward anticipation, and grip/control scores computed across sessions.',
  },
  neuro_scores: {
    label: 'Neuro Scores',
    description: 'The 11-score taxonomy computed from biometric traces. Each score has a value (0–100), confidence (0–1), status, evidence windows, and feature attributions. These feed the composite rollups.',
  },
  product_rollups: {
    label: 'Product Rollups',
    description: 'The final consumer-facing surface. Creator mode shows Reception + Organic Reach. Enterprise mode shows Paid Lift Prior, Brand Memory Prior, CTA Reception, and Synthetic Lift vs. measured lift distinction.',
  },

  // ─── Score Status ────────────────────────────────────────────────────────────

  available: {
    label: 'Available',
    description: 'Score computed normally with sufficient signal. Value and confidence are reliable for this selection.',
  },
  insufficient_data: {
    label: 'Insufficient Data',
    description: 'Not enough signal to compute the score reliably. The module ran but data quality or volume was too low to produce a confident estimate.',
  },
  unavailable: {
    label: 'Unavailable',
    description: 'Safe fallback — the module path errored, was disabled, or a required dependency was missing. This does NOT mean the creative performed poorly. Do not interpret as a negative signal.',
  },

  // ─── Neuro Scores (11 core) ──────────────────────────────────────────────────

  arrest_score: {
    label: 'Arrest Score',
    description: 'Opening stop-power proxy. Measures how strongly the first few seconds hold attention before the viewer decides to keep watching.',
    formula: '0.65 × opening_attention + 0.35 × opening_reward_proxy',
  },
  attentional_synchrony_index: {
    label: 'Attentional Synchrony Index',
    description: 'Convergence of viewer focus timing across participants. High synchrony means viewers were paying attention to the same moments at the same time.',
    formula: 'Signed synchrony → 0–100 via (x + 1) × 50. Prefers direct panel gaze pathway; falls back to aggregate synchrony proxy.',
  },
  narrative_control_score: {
    label: 'Narrative Control Score',
    description: 'How consistently cinematic grammar and transition structure guide viewer understanding. High = structure feels intentional and easy to follow.',
    formula: 'Prefers diagnostics global score. Fallback: grip-control transform → attention-velocity stability.',
  },
  blink_transport_score: {
    label: 'Blink Transport Score',
    description: 'How well blink suppression patterns align with scene transitions. High = viewers are pulled through cuts without friction.',
    formula: 'Prefers diagnostics score. Uses suppression/rebound/CTA avoidance/synchrony features. Fallback: blink inhibition mean → 0–100.',
  },
  boundary_encoding_score: {
    label: 'Boundary Encoding Score',
    description: 'How effectively scene boundaries register as meaningful transitions. High = cuts feel purposeful, not jarring or ignored.',
    formula: 'Prefers diagnostics score. Fallback: attention near cut boundaries, penalizing overload and rewarding aligned novelty.',
  },
  reward_anticipation_index: {
    label: 'Reward Anticipation Index',
    description: 'Anticipatory pull into payoff moments — do viewers lean in before rewards land? Based on pacing, blink suppression, and attention concentration dynamics.',
    formula: 'Prefers diagnostics score. Uses ramp strength + payoff release + tension-release balance − warning penalty. Fallback: reward proxy mean.',
  },
  social_transmission_score: {
    label: 'Social Transmission Score',
    description: 'Shareability proxy — separates "worth sharing" from self-relevance. Based on engagement density, attentional synchrony, and reward signal.',
    formula: '0.45 × engage_density + 0.30 × synchrony_component + 0.25 × reward_component → scaled 0–100.',
  },
  self_relevance_score: {
    label: 'Self-Relevance Score',
    description: 'How personally meaningful the content felt to viewers. Primarily survey-derived; biometric signals provide confidence weighting.',
    formula: 'Survey scale 1–5 → (avg − 1) / 4 × 100. Confidence rises with response count.',
  },
  cta_reception_score: {
    label: 'CTA Reception Score',
    description: 'How receptive viewers were to the call-to-action. Combines synchrony, narrative support, blink receptivity, reward timing, boundary coherence, and overload resilience.',
    formula: 'Prefers CTA diagnostics score. Fallback: cta_receptivity card metric → mean reward proxy near CTA markers.',
  },
  synthetic_lift_prior: {
    label: 'Synthetic Lift Prior',
    description: 'Predictive estimate of media performance lift from biometric signals. NOT a measured incrementality result — it is a prior, not proof.',
    formula: 'Prefers diagnostics score × pathway weight × calibration weight. Fallback: 50 + (golden_mean − dead_mean) × 5, clamped 0–100.',
  },
  au_friction_score: {
    label: 'AU Friction Score',
    description: 'Action unit (facial coding) based friction detector. Measures confusion, strain, tension, resistance signals from AU channel dynamics.',
    formula: 'Features: confusion/strain/tension/resistance/amusement + quality modifier. Fallback: confusion segments + AU04 trace. Diagnostic scope only — not a truth engine.',
  },

  // ─── Composite Rollups ──────────────────────────────────────────────────────

  organic_reach_prior: {
    label: 'Organic Reach Prior',
    description: 'Predicted organic distribution potential. Weighted combination of scores tied to hook power, narrative clarity, personal relevance, shareability, and CTA reception.',
    formula: '0.25 arrest + 0.20 narrative_control + 0.20 self_relevance + 0.20 social_transmission + 0.15 cta_reception',
  },
  paid_lift_prior: {
    label: 'Paid Lift Prior',
    description: 'Predicted paid media performance lift. Weights synthetic lift, CTA reception, reward anticipation, attentional synchrony, and arrest score.',
    formula: '0.30 synthetic_lift_prior + 0.25 cta_reception + 0.20 reward_anticipation + 0.15 synchrony + 0.10 arrest',
  },
  brand_memory_prior: {
    label: 'Brand Memory Prior',
    description: 'Predicted brand recall and memory encoding potential. Weights boundary encoding, narrative control, self-relevance, reward anticipation, and blink transport.',
    formula: '0.25 boundary_encoding + 0.25 narrative_control + 0.20 self_relevance + 0.15 reward_anticipation + 0.15 blink_transport',
  },

  // ─── Trace Layers ───────────────────────────────────────────────────────────

  attention_score: {
    label: 'Attention Score',
    description: 'Blink-dynamics and passive playback continuity proxy (0–100). Derived from blink rate patterns and sustained watch behavior.',
  },
  attention_velocity: {
    label: 'Attention Velocity',
    description: 'Rate of change in attention score. Positive = rising engagement, negative = dropping. Useful for spotting inflection points.',
  },
  blink_rate: {
    label: 'Blink Rate',
    description: 'Rolling blink frequency. Lower blink rate generally indicates higher cognitive engagement. Very low rates may also indicate confusion or effort.',
  },
  blink_inhibition: {
    label: 'Blink Inhibition',
    description: 'Blink suppression relative to baseline. High inhibition = viewer is visually captured by the content. A key signal for scene-level attention depth.',
  },
  reward_proxy: {
    label: 'Reward Proxy',
    description: 'Facial-coding-derived reward signal from AU (action unit) patterns (0–100). Proxy for positive affective engagement — not a direct emotion label.',
  },
  valence_proxy: {
    label: 'Valence Proxy',
    description: 'Estimated positive/negative affective tone from AU signals. Directional proxy only — do not interpret as a precise emotion classification.',
  },
  arousal_proxy: {
    label: 'Arousal Proxy',
    description: 'Estimated activation/energy level from AU and blink dynamics. High arousal can be positive (excitement) or negative (stress).',
  },
  novelty_proxy: {
    label: 'Novelty Proxy',
    description: 'Estimated novelty response from attention velocity and blink patterns. Spikes often align with scene changes or unexpected visual events.',
  },
  tracking_confidence: {
    label: 'Tracking Confidence',
    description: 'Quality/confidence estimate for webcam-derived traces. Values below ~0.6 indicate unreliable face tracking — treat corresponding signal with caution.',
  },

  // ─── Filters ─────────────────────────────────────────────────────────────────

  aggregate_view: {
    label: 'Aggregate View',
    description: 'Combines all selected sessions into a single averaged readout. Enables cross-viewer diagnostics like attentional synchrony and grip/control score.',
  },
  session_id: {
    label: 'Session ID',
    description: 'A single participant session. Required when aggregate=false. Lets you drill into one viewer\'s exact trace without averaging.',
  },
  variant_id: {
    label: 'Variant ID',
    description: 'Filters to a specific creative variant (A/B version). Only sessions matching this variant are included in the readout.',
  },
  window_ms: {
    label: 'Window (ms)',
    description: 'Smoothing bucket size for trace aggregation. 1000ms = 1-second buckets. Smaller windows = more granular but noisier. Larger = smoother but may blur short events.',
  },

  // ─── Quality Metrics ─────────────────────────────────────────────────────────

  face_ok_rate: {
    label: 'Face OK Rate',
    description: 'Fraction of frames where a valid face was detected and tracked. Below ~70% indicates significant data loss — interpret scores with caution.',
  },
  quality_badge: {
    label: 'Quality Badge',
    description: 'Overall data quality rating: high / medium / low. Based on tracking confidence, face OK rate, and usable seconds. Low quality sessions produce less reliable scores.',
  },
  usable_seconds: {
    label: 'Usable Seconds',
    description: 'Total seconds of video with valid tracking data. A low value relative to video duration means significant signal loss occurred.',
  },
  mean_tracking_confidence: {
    label: 'Mean Tracking Confidence',
    description: 'Average tracking quality across all frames. Values below ~0.65 suggest the webcam signal was unreliable. Scores derived from such data carry higher uncertainty.',
  },
  trace_source: {
    label: 'Trace Source',
    description: 'Where trace data came from. "Provided" = real biometric data. "Synthetic fallback" = model-imputed values used when real data was missing. "Mixed" = combination of both.',
  },
  low_confidence_windows: {
    label: 'Low-Confidence Windows',
    description: 'Time ranges where tracking quality dropped below threshold. Scores computed within these windows are less reliable. Shown as shaded regions on the trace chart.',
  },

  // ─── Aggregate Diagnostics ───────────────────────────────────────────────────

  grip_control_score: {
    label: 'Grip / Control Score',
    description: 'Cross-session convergence score. High = viewers responded consistently (the content "gripped" them). Low = scattered responses, inconsistent signal.',
  },
  attention_synchrony: {
    label: 'Attention Synchrony',
    description: 'Degree to which viewers\' attention traces peaked and dropped at the same moments. Higher = shared focus, lower = fragmented viewing experience.',
  },
  blink_synchrony: {
    label: 'Blink Synchrony',
    description: 'Degree to which blink suppression patterns aligned across viewers. High synchrony at a moment = that moment captured shared visual attention.',
  },
  direct_panel_gaze: {
    label: 'Direct Panel Gaze',
    description: 'Preferred synchrony pathway: gaze data from panelists is used directly to compute attentional synchrony. More reliable than fallback proxy.',
  },
  fallback_proxy: {
    label: 'Fallback Proxy',
    description: 'Secondary inference pathway used when direct signal is unavailable. Carries lower confidence. Scores derived via fallback are still valid but should be weighted accordingly.',
  },
  timeline_grammar: {
    label: 'Timeline Grammar',
    description: 'Preferred pathway for narrative control: uses per-scene transition structure and cut grammar directly from the timeline. More reliable than the fallback proxy.',
  },
  timeline_dynamics: {
    label: 'Timeline Dynamics',
    description: 'Preferred pathway for reward anticipation: uses ramp dynamics and payoff patterns from the timeline. More reliable than the fallback proxy.',
  },

  // ─── Playback / Annotations ──────────────────────────────────────────────────

  abandonment: {
    label: 'Abandonment',
    description: 'A session event where the viewer stopped watching before the video ended. The timestamp indicates where in the video the drop occurred.',
  },
  engaging_moment: {
    label: 'Engaging Moment',
    description: 'Participant explicitly marked this timestamp as engaging during post-view annotation. Count = how many participants marked it.',
  },
  confusing_moment: {
    label: 'Confusing Moment',
    description: 'Participant explicitly marked this timestamp as confusing or unclear during post-view annotation.',
  },
  stop_watching_moment: {
    label: 'Stop-Watching Moment',
    description: 'Participant marked the point where they felt like stopping. Distinct from an abandonment event — this is a self-reported impulse, not a session termination.',
  },
  cta_landed_moment: {
    label: 'CTA Landed Moment',
    description: 'Participant marked this as the moment the call-to-action felt clear and landed. Useful for validating CTA placement timing.',
  },

  // ─── Prediction Overlay ──────────────────────────────────────────────────────

  prediction_overlay: {
    label: 'Prediction Overlay',
    description: 'Model-predicted attention and reward traces overlaid on measured data as dashed lines. Useful for comparing what the model expected vs. what actually happened.',
  },

  // ─── Scene Diagnostics ───────────────────────────────────────────────────────

  golden_scene: {
    label: 'Golden Scene',
    description: 'The peak sustained engagement window — highest combined reward and attention across the video. The moment the creative was working best.',
  },
  hook_strength: {
    label: 'Hook Strength',
    description: 'Opening-window performance and viewer retention. Measures how strongly the first few seconds held attention before the skip/abandon decision point.',
  },
  cta_receptivity: {
    label: 'CTA Receptivity',
    description: 'Attention and reward signal quality around the CTA window. High = viewers were primed and attentive when the call-to-action appeared.',
  },
  attention_drop_scene: {
    label: 'Attention Drop Scene',
    description: 'The scene with the largest sustained negative attention delta. Likely the weakest creative moment — where viewer engagement fell most sharply.',
  },
  confusion_scene: {
    label: 'Confusion Scene',
    description: 'A window showing friction indicators: falling attention combined with blink/AU patterns associated with cognitive effort or unclear messaging.',
  },
  recovery_scene: {
    label: 'Recovery Scene',
    description: 'A later segment where attention rebounds after a drop. Indicates the creative regained viewer interest — useful context for edit decisions.',
  },

  // ─── Evidence / Features ─────────────────────────────────────────────────────

  evidence_windows: {
    label: 'Evidence Windows',
    description: 'Specific time ranges that drove this score. Each window has a start/end time, confidence, and reason code. Click "Seek" to jump to that moment in the video.',
  },
  top_feature_contributions: {
    label: 'Top Feature Contributions',
    description: 'The signal features that most influenced this score and their contribution weights. Positive = pushed score up, negative = pulled score down.',
  },
  provenance: {
    label: 'Provenance',
    description: 'The computation pathway used to generate this score. Records whether the preferred diagnostic path, a fallback path, or a synthetic fallback was used.',
  },
  model_version: {
    label: 'Model Version',
    description: 'The version of the scoring model used. Important for comparing results across different readout runs — scores may shift between model versions.',
  },

  // ─── Segment Types ───────────────────────────────────────────────────────────

  dead_zones: {
    label: 'Dead Zones',
    description: 'Sustained windows of low attention and low reward signal. The creative is losing the viewer here. Duration and depth indicate severity.',
  },
  attention_gain_segments: {
    label: 'Attention Gains',
    description: 'Sustained rises in the attention trace. The creative is recapturing or building viewer engagement in these windows.',
  },
  attention_loss_segments: {
    label: 'Attention Losses',
    description: 'Sustained declines in the attention trace. These windows are candidates for creative editing or restructuring.',
  },
  confusion_segments: {
    label: 'Confusion Segments',
    description: 'Windows with blink/AU/velocity patterns associated with confusion or cognitive friction — where messaging clarity may have broken down.',
  },
};
