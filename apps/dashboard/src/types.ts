export type TraceBucket = {
  bucket_start_ms: number;
  samples: number;
  mean_brightness: number;
  mean_blur?: number;
  face_ok_rate: number;
  mean_face_presence_confidence?: number;
  landmarks_ok_rate: number;
  mean_landmarks_confidence?: number;
  blink_rate: number;
  mean_rolling_blink_rate?: number;
  mean_blink_inhibition_score?: number;
  blink_inhibition_active_rate?: number;
  mean_blink_baseline_rate?: number;
  mean_dial: number | null;
  mean_reward_proxy?: number | null;
  mean_gaze_on_screen_proxy?: number | null;
  mean_gaze_on_screen_confidence?: number | null;
  mean_fps?: number | null;
  mean_fps_stability?: number | null;
  mean_face_visible_pct?: number | null;
  mean_occlusion_score?: number | null;
  mean_head_pose_valid_pct?: number | null;
  mean_quality_score?: number | null;
  mean_quality_confidence?: number | null;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  mean_au_norm: Record<string, number>;
};

export type SceneMetric = {
  scene_index: number;
  label: string | null;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  start_ms: number;
  end_ms: number;
  samples: number;
  face_ok_rate: number;
  blink_rate: number;
  mean_au12: number;
  mean_reward_proxy?: number | null;
};

export type QualityOverlayBucket = {
  bucket_start_ms: number;
  samples: number;
  mean_brightness: number;
  mean_blur: number;
  mean_fps_stability?: number | null;
  mean_face_visible_pct?: number | null;
  mean_occlusion_score?: number | null;
  mean_head_pose_valid_pct?: number | null;
  mean_quality_score?: number | null;
  mean_quality_confidence?: number | null;
};

export type QCStats = {
  sessions_count: number;
  participants_count: number;
  total_trace_points: number;
  missing_trace_sessions: number;
  face_ok_rate: number;
  landmarks_ok_rate: number;
  mean_brightness: number;
};

export type AnnotationMarker = {
  id: string;
  session_id: string;
  video_id: string;
  marker_type: 'engaging_moment' | 'confusing_moment' | 'stop_watching_moment' | 'cta_landed_moment';
  video_time_ms: number;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  note: string | null;
  created_at: string;
};

export type AnnotationOverlayMarker = {
  marker_type: AnnotationMarker['marker_type'];
  video_time_ms: number;
  count: number;
  density: number;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
};

export type TelemetryOverlayKind = 'pause' | 'seek' | 'abandonment';

export type TelemetryOverlayMarker = {
  kind: TelemetryOverlayKind;
  video_time_ms: number;
  count: number;
  density: number;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  event_types: string[];
};

export type TimestampSummary = {
  video_time_ms: number;
  count: number;
  density: number;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
};

export type SurveyResponse = {
  id: string;
  session_id: string;
  question_key: string;
  response_text: string | null;
  response_number: number | null;
  response_json: Record<string, unknown> | null;
  created_at: string;
};

export type PlaybackTelemetryEvent = {
  id: string;
  session_id: string;
  video_id: string;
  event_type: string;
  video_time_ms: number;
  wall_time_ms?: number | null;
  client_monotonic_ms?: number | null;
  details?: Record<string, unknown> | null;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  created_at: string;
};

export type VideoSummary = {
  video_id: string;
  trace_buckets: TraceBucket[];
  passive_traces?: TraceBucket[];
  quality_overlays?: QualityOverlayBucket[];
  scene_metrics: SceneMetric[];
  scene_aligned_summaries?: SceneMetric[];
  qc_stats: QCStats;
  annotations: AnnotationMarker[];
  explicit_labels?: AnnotationMarker[];
  survey_responses?: SurveyResponse[];
  playback_telemetry?: PlaybackTelemetryEvent[];
};

export type VideoCatalogSession = {
  id: string;
  participant_id: string;
  participant_external_id?: string | null;
  participant_demographics?: Record<string, unknown> | null;
  status: string;
  created_at: string;
};

export type VideoCatalogItem = {
  video_id: string;
  study_id: string;
  study_name: string;
  title: string;
  source_url?: string | null;
  duration_ms?: number | null;
  created_at: string;
  sessions_count: number;
  completed_sessions_count: number;
  abandoned_sessions_count: number;
  participants_count: number;
  last_session_id?: string | null;
  last_session_at?: string | null;
  last_session_status?: string | null;
  latest_trace_at?: string | null;
  recent_sessions: VideoCatalogSession[];
};

export type VideoCatalogResponse = {
  items: VideoCatalogItem[];
};

export type NeuroObservabilityLatestSnapshot = {
  recorded_at: string | null;
  video_id: string | null;
  variant_id: string | null;
  model_signature: string | null;
  drift_status: string | null;
  missing_signal_rate: number | null;
  fallback_rate: number | null;
  confidence_mean: number | null;
  metrics_exceeding_threshold: string[];
};

export type NeuroObservabilityStatus = {
  status: string;
  enabled: boolean;
  history_enabled: boolean;
  history_entry_count: number;
  history_max_entries: number;
  drift_alert_threshold: number;
  recent_window: number;
  recent_snapshot_count: number;
  recent_drift_alert_count: number;
  recent_drift_alert_rate: number | null;
  mean_missing_signal_rate: number | null;
  mean_fallback_rate: number | null;
  mean_confidence: number | null;
  latest_snapshot: NeuroObservabilityLatestSnapshot | null;
  warnings: string[];
};

export type CaptureArchiveFailureCodeCount = {
  error_code: string;
  count: number;
};

export type CaptureArchiveObservabilityStatus = {
  status: string;
  enabled: boolean;
  purge_enabled: boolean;
  retention_days: number;
  purge_batch_size: number;
  encryption_mode: string;
  ingestion_event_count: number;
  success_count: number;
  failure_count: number;
  failure_rate: number | null;
  recent_window_hours: number;
  recent_success_count: number;
  recent_failure_count: number;
  recent_failure_rate: number | null;
  total_archives: number;
  total_frames: number;
  total_frame_pointers: number;
  total_uncompressed_bytes: number;
  total_compressed_bytes: number;
  oldest_archive_at: string | null;
  newest_archive_at: string | null;
  top_failure_codes: CaptureArchiveFailureCodeCount[];
  warnings: string[];
};

export type FrontendDiagnosticEvent = {
  id: string;
  surface: string;
  page: string;
  route?: string | null;
  severity: 'info' | 'warning' | 'error' | string;
  event_type: string;
  error_code?: string | null;
  message?: string | null;
  context?: Record<string, unknown> | null;
  session_id?: string | null;
  video_id?: string | null;
  study_id?: string | null;
  created_at: string;
};

export type FrontendDiagnosticEventsResponse = {
  items: FrontendDiagnosticEvent[];
};

export type FrontendDiagnosticErrorCount = {
  event_type: string;
  error_code: string;
  count: number;
};

export type FrontendDiagnosticSummary = {
  status: string;
  window_hours: number;
  total_events: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  active_pages: string[];
  last_event_at: string | null;
  top_errors: FrontendDiagnosticErrorCount[];
  warnings: string[];
};

export type FrontendDiagnosticEventInput = {
  surface: 'watchlab' | 'dashboard' | 'unknown';
  page: 'study' | 'readout' | 'predictor' | 'observability' | 'upload' | 'unknown';
  route?: string;
  severity?: 'info' | 'warning' | 'error';
  event_type: string;
  error_code?: string;
  message?: string;
  context?: Record<string, unknown>;
  session_id?: string;
  video_id?: string;
  study_id?: string;
};

export type TimelinePoint = {
  tMs: number;
  tSec: number;
  attention: number;
  dial: number | null;
  blinkRate: number;
  blinkInhibition: number;
  rewardProxy: number | null;
  gazeProxy: number | null;
  qualityScore: number | null;
  qualityConfidence: number | null;
  faceOkRate: number;
  sceneId: string | null;
  cutId: string | null;
  ctaId: string | null;
  au12: number;
  au6: number;
  au4: number;
};

export type EngagementPeak = {
  tSec: number;
  score: number;
  rewardProxy: number | null;
  sceneLabel: string;
};

export type DeadZone = {
  startSec: number;
  endSec: number;
  durationSec: number;
  meanAttention: number;
  frictionScore: number;
  sceneLabel: string;
};

export type ReadoutScene = {
  scene_index: number;
  start_ms: number;
  end_ms: number;
  label?: string | null;
  thumbnail_url?: string | null;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
};

export type ReadoutCut = {
  cut_id: string;
  start_ms: number;
  end_ms: number;
  scene_id?: string | null;
  cta_id?: string | null;
  label?: string | null;
};

export type ReadoutCtaMarker = {
  cta_id: string;
  video_time_ms: number;
  start_ms?: number | null;
  end_ms?: number | null;
  scene_id?: string | null;
  cut_id?: string | null;
  label?: string | null;
};

export type ReadoutTracePoint = {
  video_time_ms: number;
  value: number | null;
  median?: number | null;
  ci_low?: number | null;
  ci_high?: number | null;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
};

export type ReadoutAUChannel = {
  au_name: string;
  points: ReadoutTracePoint[];
};

export type ReadoutTraces = {
  attention_score: ReadoutTracePoint[];
  attention_velocity: ReadoutTracePoint[];
  blink_rate: ReadoutTracePoint[];
  blink_inhibition: ReadoutTracePoint[];
  reward_proxy: ReadoutTracePoint[];
  valence_proxy: ReadoutTracePoint[];
  arousal_proxy: ReadoutTracePoint[];
  novelty_proxy: ReadoutTracePoint[];
  tracking_confidence: ReadoutTracePoint[];
  au_channels: ReadoutAUChannel[];
};

export type ReadoutSegment = {
  start_video_time_ms: number;
  end_video_time_ms: number;
  metric: string;
  magnitude: number;
  confidence: number | null;
  reason_codes: string[];
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  distance_to_cta_ms?: number | null;
  cta_window?: 'pre_cta' | 'on_cta' | 'post_cta' | null;
  score?: number | null;
  notes?: string | null;
};

export type ReadoutSegments = {
  attention_gain_segments: ReadoutSegment[];
  attention_loss_segments: ReadoutSegment[];
  golden_scenes: ReadoutSegment[];
  dead_zones: ReadoutSegment[];
  confusion_segments: ReadoutSegment[];
};

export type ReadoutDiagnosticCard = {
  card_type:
    | 'golden_scene'
    | 'hook_strength'
    | 'cta_receptivity'
    | 'attention_drop_scene'
    | 'confusion_scene'
    | 'recovery_scene';
  scene_index?: number | null;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  scene_label?: string | null;
  scene_thumbnail_url?: string | null;
  start_video_time_ms: number;
  end_video_time_ms: number;
  primary_metric: string;
  primary_metric_value: number;
  why_flagged: string;
  confidence?: number | null;
  reason_codes: string[];
};

export type ReadoutAnnotationSummary = {
  total_annotations: number;
  engaging_moment_count: number;
  confusing_moment_count: number;
  stop_watching_moment_count: number;
  cta_landed_moment_count: number;
  marker_density: AnnotationOverlayMarker[];
  top_engaging_timestamps: TimestampSummary[];
  top_confusing_timestamps: TimestampSummary[];
};

export type ReadoutSurveySummary = {
  responses_count: number;
  overall_interest_mean?: number | null;
  recall_comprehension_mean?: number | null;
  desire_to_continue_or_take_action_mean?: number | null;
  comment_count: number;
};

export type ReadoutQualitySummary = {
  sessions_count: number;
  participants_count: number;
  total_trace_points: number;
  face_ok_rate: number;
  mean_brightness: number;
  mean_tracking_confidence?: number | null;
  mean_quality_score?: number | null;
  low_confidence_windows: number;
  usable_seconds?: number | null;
  quality_badge?: 'high' | 'medium' | 'low' | null;
  trace_source?: 'provided' | 'synthetic_fallback' | 'mixed' | 'unknown' | null;
};

export type ReadoutLowConfidenceWindow = {
  start_video_time_ms: number;
  end_video_time_ms: number;
  mean_tracking_confidence?: number | null;
  quality_flags?: string[];
};

export type ReadoutTimebase = {
  window_ms: number;
  step_ms: number;
};

export type ReadoutContext = {
  scenes: ReadoutScene[];
  cuts: ReadoutCut[];
  cta_markers: ReadoutCtaMarker[];
};

export type ReadoutLabels = {
  annotations: AnnotationMarker[];
  survey_summary?: ReadoutSurveySummary | null;
  annotation_summary?: ReadoutAnnotationSummary | null;
};

export type ReadoutQuality = {
  session_quality_summary: ReadoutQualitySummary;
  low_confidence_windows: ReadoutLowConfidenceWindow[];
};

export type ReliabilityScoreDetail = {
  machine_name: string;
  status: string;
  scalar_value?: number | null;
  confidence?: number | null;
  pathway?: string | null;
  issues: string[];
  score_reliability: number;
};

export type ReadoutReliabilityScore = {
  overall: number;
  availability_score: number;
  range_validity_score: number;
  pathway_quality_score: number;
  signal_health_score: number;
  duration_accuracy_score: number;
  rollup_integrity_score: number;
  scores_available: number;
  scores_total: number;
  score_details: ReliabilityScoreDetail[];
  issues: string[];
  model_version: string;
};

export type AttentionalSynchronyPathway =
  | 'direct_panel_gaze'
  | 'fallback_proxy'
  | 'insufficient_data';

export type AttentionalSynchronyTimelineScore = {
  start_ms: number;
  end_ms: number;
  score: number;
  confidence: number;
  pathway: AttentionalSynchronyPathway;
  reason: string;
};

export type AttentionalSynchronyExtrema = {
  start_ms: number;
  end_ms: number;
  score: number;
  reason: string;
};

export type AttentionalSynchronyDiagnostics = {
  pathway: AttentionalSynchronyPathway;
  global_score?: number | null;
  confidence?: number | null;
  segment_scores: AttentionalSynchronyTimelineScore[];
  peaks: AttentionalSynchronyExtrema[];
  valleys: AttentionalSynchronyExtrema[];
  evidence_summary: string;
  signals_used: string[];
};

export type NarrativeControlPathway =
  | 'timeline_grammar'
  | 'fallback_proxy'
  | 'insufficient_data';

export type NarrativeControlSceneScore = {
  start_ms: number;
  end_ms: number;
  score: number;
  confidence: number;
  scene_id?: string | null;
  scene_label?: string | null;
  fragmentation_index?: number | null;
  boundary_density?: number | null;
  motion_continuity?: number | null;
  ordering_pattern?: 'context_before_face' | 'face_before_context' | 'balanced' | null;
  summary: string;
};

export type NarrativeControlMomentContribution = {
  start_ms: number;
  end_ms: number;
  contribution: number;
  category: string;
  reason: string;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
};

export type NarrativeControlHeuristicCheck = {
  heuristic_key: string;
  passed: boolean;
  score_delta: number;
  reason: string;
  start_ms?: number | null;
  end_ms?: number | null;
};

export type NarrativeControlDiagnostics = {
  pathway: NarrativeControlPathway;
  global_score?: number | null;
  confidence?: number | null;
  scene_scores: NarrativeControlSceneScore[];
  disruption_penalties: NarrativeControlMomentContribution[];
  reveal_structure_bonuses: NarrativeControlMomentContribution[];
  top_contributing_moments: NarrativeControlMomentContribution[];
  heuristic_checks: NarrativeControlHeuristicCheck[];
  evidence_summary: string;
  signals_used: string[];
};

export type RewardAnticipationPathway =
  | 'timeline_dynamics'
  | 'fallback_proxy'
  | 'insufficient_data';

export type RewardAnticipationTimelineWindowType = 'anticipation_ramp' | 'payoff_window';

export type RewardAnticipationTimelineWindow = {
  start_ms: number;
  end_ms: number;
  score: number;
  confidence: number;
  window_type: RewardAnticipationTimelineWindowType;
  reason: string;
  ramp_slope?: number | null;
  reward_delta?: number | null;
  tension_level?: number | null;
  release_level?: number | null;
};

export type RewardAnticipationWarningSeverity = 'low' | 'medium' | 'high';

export type RewardAnticipationWarning = {
  warning_key: string;
  severity: RewardAnticipationWarningSeverity;
  message: string;
  start_ms?: number | null;
  end_ms?: number | null;
  metric_value?: number | null;
};

export type RewardAnticipationDiagnostics = {
  pathway: RewardAnticipationPathway;
  global_score?: number | null;
  confidence?: number | null;
  anticipation_ramps: RewardAnticipationTimelineWindow[];
  payoff_windows: RewardAnticipationTimelineWindow[];
  warnings: RewardAnticipationWarning[];
  anticipation_strength?: number | null;
  payoff_release_strength?: number | null;
  tension_release_balance?: number | null;
  evidence_summary: string;
  signals_used: string[];
};

export type SyntheticLiftPriorPathway =
  | 'taxonomy_regression'
  | 'fallback_proxy'
  | 'insufficient_data';

export type SyntheticLiftCalibrationStatus =
  | 'uncalibrated'
  | 'provisional'
  | 'geox_calibrated'
  | 'truth_layer_unavailable';

export type SyntheticLiftPriorFeatureInput = {
  feature_name: string;
  source: 'taxonomy' | 'legacy_performance' | 'calibration';
  raw_value: number;
  normalized_value: number;
  weight: number;
};

export type SyntheticLiftPriorTimelineWindow = {
  start_ms: number;
  end_ms: number;
  score: number;
  confidence: number;
  reason: string;
  contribution?: number | null;
};

export type SyntheticLiftPriorDiagnostics = {
  pathway: SyntheticLiftPriorPathway;
  global_score?: number | null;
  confidence?: number | null;
  predicted_incremental_lift_pct?: number | null;
  predicted_iroas?: number | null;
  incremental_lift_ci_low?: number | null;
  incremental_lift_ci_high?: number | null;
  iroas_ci_low?: number | null;
  iroas_ci_high?: number | null;
  uncertainty_band?: number | null;
  calibration_status: SyntheticLiftCalibrationStatus;
  calibration_observation_count: number;
  calibration_last_updated_at?: string | null;
  model_version: string;
  segment_scores: SyntheticLiftPriorTimelineWindow[];
  feature_inputs: SyntheticLiftPriorFeatureInput[];
  evidence_summary: string;
  signals_used: string[];
};

export type ReadoutAggregateMetrics = {
  attention_synchrony?: number | null;
  blink_synchrony?: number | null;
  grip_control_score?: number | null;
  attentional_synchrony?: AttentionalSynchronyDiagnostics | null;
  narrative_control?: NarrativeControlDiagnostics | null;
  reward_anticipation?: RewardAnticipationDiagnostics | null;
  synthetic_lift_prior?: SyntheticLiftPriorDiagnostics | null;
  ci_method?: 'sem_95' | null;
  included_sessions: number;
  downweighted_sessions: number;
};

export type NeuroScoreStatus = 'available' | 'unavailable' | 'insufficient_data';

export type NeuroScoreMachineName =
  | 'arrest_score'
  | 'attentional_synchrony_index'
  | 'narrative_control_score'
  | 'blink_transport_score'
  | 'boundary_encoding_score'
  | 'reward_anticipation_index'
  | 'social_transmission_score'
  | 'self_relevance_score'
  | 'cta_reception_score'
  | 'synthetic_lift_prior'
  | 'au_friction_score';

export type NeuroRollupMachineName =
  | 'organic_reach_prior'
  | 'paid_lift_prior'
  | 'brand_memory_prior';

export type NeuroEvidenceWindow = {
  start_ms: number;
  end_ms: number;
  reason: string;
};

export type NeuroFeatureContribution = {
  feature_name: string;
  contribution: number;
  rationale?: string | null;
};

export type NeuroScoreContract = {
  machine_name: NeuroScoreMachineName;
  display_label: string;
  scalar_value: number | null;
  confidence: number | null;
  status: NeuroScoreStatus;
  evidence_windows: NeuroEvidenceWindow[];
  top_feature_contributions: NeuroFeatureContribution[];
  model_version: string;
  provenance: string;
  claim_safe_description: string;
};

export type NeuroCompositeRollup = {
  machine_name: NeuroRollupMachineName;
  display_label: string;
  scalar_value: number | null;
  confidence: number | null;
  status: NeuroScoreStatus;
  component_scores: NeuroScoreMachineName[];
  component_weights: Record<string, number>;
  model_version: string;
  provenance: string;
  claim_safe_description: string;
};

export type LegacyScoreAdapter = {
  legacy_output: 'emotion' | 'attention';
  mapped_machine_name: NeuroScoreMachineName;
  scalar_value: number | null;
  confidence: number | null;
  status: NeuroScoreStatus;
  notes?: string | null;
};

export type NeuroRegistryEntry = {
  machine_name: NeuroScoreMachineName;
  display_label: string;
  claim_safe_description: string;
  builder_key: string;
};

export type NeuroRollupRegistryEntry = {
  machine_name: NeuroRollupMachineName;
  display_label: string;
  claim_safe_description: string;
  builder_key: string;
};

export type NeuroScoreTaxonomy = {
  schema_version: string;
  scores: {
    arrest_score: NeuroScoreContract;
    attentional_synchrony_index: NeuroScoreContract;
    narrative_control_score: NeuroScoreContract;
    blink_transport_score: NeuroScoreContract;
    boundary_encoding_score: NeuroScoreContract;
    reward_anticipation_index: NeuroScoreContract;
    social_transmission_score: NeuroScoreContract;
    self_relevance_score: NeuroScoreContract;
    cta_reception_score: NeuroScoreContract;
    synthetic_lift_prior: NeuroScoreContract;
    au_friction_score: NeuroScoreContract;
  };
  rollups: {
    organic_reach_prior: NeuroCompositeRollup;
    paid_lift_prior: NeuroCompositeRollup;
    brand_memory_prior: NeuroCompositeRollup;
  };
  registry: NeuroRegistryEntry[];
  rollup_registry: NeuroRollupRegistryEntry[];
  legacy_score_adapters: LegacyScoreAdapter[];
};

export type ProductRollupMode = 'creator' | 'enterprise';

export type ProductRollupWarningSeverity = 'low' | 'medium' | 'high';

export type ProductLiftTruthStatus = 'unavailable' | 'pending' | 'measured';

export type ProductScoreSummary = {
  metric_key: string;
  display_label: string;
  scalar_value: number | null;
  confidence: number | null;
  status: NeuroScoreStatus;
  explanation: string;
  source_metrics: string[];
};

export type ProductRollupWarning = {
  warning_key: string;
  severity: ProductRollupWarningSeverity;
  message: string;
  source_metrics: string[];
};

export type CreatorProductRollups = {
  reception_score: ProductScoreSummary;
  organic_reach_prior: ProductScoreSummary;
  explanations: string[];
  warnings: ProductRollupWarning[];
};

export type ProductLiftComparison = {
  synthetic_lift_prior: ProductScoreSummary;
  predicted_incremental_lift_pct?: number | null;
  predicted_iroas?: number | null;
  predicted_incremental_lift_ci_low?: number | null;
  predicted_incremental_lift_ci_high?: number | null;
  measured_lift_status: ProductLiftTruthStatus;
  measured_incremental_lift_pct?: number | null;
  measured_iroas?: number | null;
  calibration_status?:
    | 'uncalibrated'
    | 'provisional'
    | 'geox_calibrated'
    | 'truth_layer_unavailable'
    | null;
  note: string;
};

export type EnterpriseDecisionSupport = {
  media_team_summary: string;
  creative_team_summary: string;
};

export type EnterpriseProductRollups = {
  paid_lift_prior: ProductScoreSummary;
  brand_memory_prior: ProductScoreSummary;
  cta_reception_score: ProductScoreSummary;
  synthetic_lift_prior: ProductScoreSummary;
  synthetic_vs_measured_lift: ProductLiftComparison;
  decision_support: EnterpriseDecisionSupport;
};

export type ProductRollupPresentation = {
  mode: ProductRollupMode;
  workspace_tier: string;
  enabled_modes: ProductRollupMode[];
  mode_resolution_note?: string | null;
  source_schema_version: string;
  creator?: CreatorProductRollups | null;
  enterprise?: EnterpriseProductRollups | null;
};

export type VideoReadout = {
  schema_version: string;
  video_id: string;
  source_url?: string | null;
  source_url_reachable?: boolean | null;
  has_sufficient_watch_data?: boolean;
  variant_id?: string | null;
  session_id?: string | null;
  aggregate: boolean;
  duration_ms: number;
  timebase: ReadoutTimebase;
  context: ReadoutContext;
  traces: ReadoutTraces;
  segments: ReadoutSegments;
  labels: ReadoutLabels;
  quality: ReadoutQuality;
  aggregate_metrics?: ReadoutAggregateMetrics | null;
  playback_telemetry?: PlaybackTelemetryEvent[];
  reliability_score?: ReadoutReliabilityScore | null;
  neuro_scores?: NeuroScoreTaxonomy | null;
  product_rollups?: ProductRollupPresentation | null;
  legacy_score_adapters?: LegacyScoreAdapter[];

  // Compatibility mirrors for existing dashboard paths during migration.
  scenes?: ReadoutScene[];
  cuts?: ReadoutCut[];
  cta_markers?: ReadoutCtaMarker[];
  diagnostics?: ReadoutDiagnosticCard[];
  quality_summary?: ReadoutQualitySummary;
  annotations?: AnnotationMarker[];
  annotation_summary?: ReadoutAnnotationSummary;
  survey_summary?: ReadoutSurveySummary;
};

export type ReadoutVideoMetadata = {
  video_id: string;
  study_id: string;
  study_name?: string | null;
  title: string;
  source_url?: string | null;
  duration_ms?: number | null;
  variant_id?: string | null;
  aggregate: boolean;
  session_id?: string | null;
  window_ms: number;
  generated_at: string;
};

export type RewardProxyPeak = {
  video_time_ms: number;
  reward_proxy: number;
  scene_id?: string | null;
  cut_id?: string | null;
  cta_id?: string | null;
  tracking_confidence?: number | null;
};

export type ReadoutExportJson = {
  video_metadata: ReadoutVideoMetadata;
  scenes: ReadoutScene[];
  cta_markers: ReadoutCtaMarker[];
  segments: ReadoutSegments;
  diagnostics: ReadoutDiagnosticCard[];
  reward_proxy_peaks: RewardProxyPeak[];
  quality_summary: ReadoutQualitySummary;
  annotation_summary: ReadoutAnnotationSummary;
  survey_summary: ReadoutSurveySummary;
  neuro_scores?: NeuroScoreTaxonomy | null;
  product_rollups?: ProductRollupPresentation | null;
  legacy_score_adapters?: LegacyScoreAdapter[];
};

export type CompactReadoutHighlights = {
  top_reward_proxy_peak?: RewardProxyPeak | null;
  top_attention_gain_segment?: ReadoutSegment | null;
  top_attention_loss_segment?: ReadoutSegment | null;
  top_golden_scene?: ReadoutSegment | null;
  top_dead_zone?: ReadoutSegment | null;
};

export type CompactReadoutReport = {
  video_metadata: ReadoutVideoMetadata;
  scenes: ReadoutScene[];
  cta_markers: ReadoutCtaMarker[];
  attention_gain_segments: ReadoutSegment[];
  attention_loss_segments: ReadoutSegment[];
  golden_scenes: ReadoutSegment[];
  dead_zones: ReadoutSegment[];
  reward_proxy_peaks: RewardProxyPeak[];
  quality_summary: ReadoutQualitySummary;
  annotation_summary: ReadoutAnnotationSummary;
  survey_summary: ReadoutSurveySummary;
  highlights: CompactReadoutHighlights;
  neuro_scores?: NeuroScoreTaxonomy | null;
  product_rollups?: ProductRollupPresentation | null;
  legacy_score_adapters?: LegacyScoreAdapter[];
};

export type ReadoutExportPackage = {
  video_metadata: ReadoutVideoMetadata;
  per_timepoint_csv: string;
  readout_json: ReadoutExportJson;
  compact_report: CompactReadoutReport;
  edit_suggestions_stub?: Record<string, unknown> | null;
};

export type ReadoutTimelinePoint = {
  tMs: number;
  tSec: number;
  sceneId: string | null;
  cutId: string | null;
  ctaId: string | null;
  attentionScore: number | null;
  attentionScoreMedian?: number | null;
  attentionScoreCiLow?: number | null;
  attentionScoreCiHigh?: number | null;
  attentionVelocity: number | null;
  blinkRate: number | null;
  blinkInhibition: number | null;
  rewardProxy: number | null;
  rewardProxyMedian?: number | null;
  rewardProxyCiLow?: number | null;
  rewardProxyCiHigh?: number | null;
  valenceProxy: number | null;
  arousalProxy: number | null;
  noveltyProxy: number | null;
  trackingConfidence: number | null;
  predictedAttentionScore?: number | null;
  predictedRewardProxy?: number | null;
  predictedBlinkInhibition?: number | null;
  auValues: Record<string, number | null>;
};

export type ConfidenceWindow = {
  startSec: number;
  endSec: number;
  qualityFlags?: string[];
};

export type TraceLayerVisibility = {
  attentionScore: boolean;
  attentionVelocity: boolean;
  blinkRate: boolean;
  blinkInhibition: boolean;
  rewardProxy: boolean;
  valenceProxy: boolean;
  arousalProxy: boolean;
  noveltyProxy: boolean;
  trackingConfidence: boolean;
};

export type PredictTracePoint = {
  t_sec: number;
  reward_proxy: number | null;
  dopamine_score?: number | null;
  attention: number | null;
  blink_inhibition: number;
  dial: number;
  attention_velocity?: number | null;
  blink_rate?: number | null;
  valence_proxy?: number | null;
  arousal_proxy?: number | null;
  novelty_proxy?: number | null;
  tracking_confidence?: number | null;
};

export type PredictResponse = {
  model_artifact: string;
  predictions: PredictTracePoint[];
  resolved_video_url: string | null;
  prediction_backend: string;
  video_id: string | null;
};

export type PredictJobStatus = {
  job_id: string;
  status: 'pending' | 'downloading' | 'running' | 'uploading' | 'done' | 'failed';
  stage_label: string;
  result: PredictResponse | null;
  error: string | null;
};

export type PredictJobsObservabilityStatus = {
  active_jobs: number;
  queued_total: number;
  completed_total: number;
  failed_total: number;
  github_upload_attempts: number;
  github_upload_successes: number;
  github_upload_failures: number;
  github_upload_success_rate: number | null;
};

// ---------------------------------------------------------------------------
// Analyst View types
// ---------------------------------------------------------------------------

export type AnalystSurveyResponseItem = {
  question_key: string;
  response_text: string | null;
  response_number: number | null;
  response_json: Record<string, unknown> | null;
};

export type AnalystSession = {
  session_id: string;
  participant_external_id: string | null;
  participant_demographics: Record<string, unknown> | null;
  status: string;
  created_at: string;
  ended_at: string | null;
  survey_responses: AnalystSurveyResponseItem[];
  has_capture: boolean;
  capture_frame_count: number;
  capture_created_at: string | null;
  trace_point_count: number;
};

export type AnalystSessionsResponse = {
  video_id: string;
  video_title: string;
  sessions: AnalystSession[];
  total_sessions: number;
  last_updated_at: string | null;
};
