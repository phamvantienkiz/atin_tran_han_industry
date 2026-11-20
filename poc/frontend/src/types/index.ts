export interface ZonePoint {
  x: number;
  y: number;
}

export type FeatureType = 'zone_presence' | 'zone_intrusion';
export type StreamMode = 'mjpeg' | 'snapshot';
export type UiColor = 'green' | 'yellow' | 'red' | 'idle';
export type PresenceStatus = 'present' | 'leaving' | 'empty' | 'alert' | 'idle';

export interface Camera {
  id: string;
  channel: number;
  name: string;
  zone_name?: string;
  note?: string;
  subtype: number;
  mode: StreamMode;
  feature_type?: FeatureType;
  grace_seconds?: number;
  warning_seconds?: number;
  enabled: boolean;
  zone: ZonePoint[];
}

export interface CameraCreatePayload {
  channel: number;
  name: string;
  zone_name?: string;
  note?: string;
  subtype: number;
  mode: StreamMode;
  feature_type?: FeatureType;
  grace_seconds?: number;
  warning_seconds?: number;
  enabled?: boolean;
}

export interface CameraUpdatePayload {
  channel?: number;
  name?: string;
  zone_name?: string;
  note?: string;
  subtype?: number;
  mode?: StreamMode;
  feature_type?: FeatureType;
  grace_seconds?: number;
  warning_seconds?: number;
  enabled?: boolean;
}

export interface DetectedPerson {
  id?: number;
  track_id?: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  cx: number;
  cy: number;
  foot_x?: number;
  foot_y?: number;
  conf: number;
  in_zone: boolean;
  predicted?: boolean;
}

export interface BboxWsMessage {
  type: 'bbox';
  cam_id: string;
  frame_id?: number;
  ts_capture?: number;
  delay_ms?: number;
  inference_ms?: number;
  in_zone_count?: number;
  persons: DetectedPerson[];
}

export interface HudWsMessage {
  type: 'hud';
  cam_id: string;
  has_zone: boolean;
  status: PresenceStatus;
  ui_color: UiColor;
  status_label: string;
  sub_label: string;
  polygon_label: string;
  alert_count: number;
  total_alert_seconds: number;
  session_duration_seconds: number;
  in_zone_count?: number;
  active_provider?: string;
  timeline?: TimelineSegment[];
}

export interface TimelineSegment {
  start: number;
  end: number;
  color: 'green' | 'yellow' | 'red';
}

export interface CameraDetection {
  cam_id: string;
  has_zone: boolean;
  person_in_zone: boolean;
  in_zone_count: number;
  total_persons: number;
  persons: DetectedPerson[];
  dwell_seconds?: number;
  event_triggered?: boolean;
  status: PresenceStatus;
  ui_color: UiColor;
  status_label: string;
  sub_label: string;
  polygon_label: string;
  empty_duration: number;
  alert_count: number;
  total_alert_seconds: number;
  session_duration_seconds: number;
  timeline: TimelineSegment[];
  inference_ms?: number;
  delay_ms?: number;
  active_provider?: string;
  updated_at: number;
  _client_ts?: number;
  error?: string;
}

export interface CameraProbeResult {
  id: string;
  online: boolean;
  status_code?: number;
  latency_ms: number | null;
  bytes?: number;
  error?: string;
  source?: string;
}

export interface AppConfig {
  nvr_host: string;
  nvr_port: number;
  project: string;
  environment: string;
  atin_vms_enabled: boolean;
  timeline_window_sec?: number;
  ws_path?: string;
  ai_runtime?: string;
  active_provider?: string;
  grace_seconds?: number;
  warning_seconds?: number;
  bbox_stale_seconds?: number;
  stream_sync_delay_ms?: number;
  ws_legacy_payload?: boolean;
}

export interface ActiveRecordJob {
  job_id: string;
  cam_id: string;
  channel: number;
  filename: string;
  status: string;
  remaining_sec: number;
  elapsed_sec?: number;
  duration_sec?: number;
}

export interface VideoItem {
  filename: string;
  size_bytes: number;
  created_at: number;
  duration_sec?: number;
  width?: number;
  height?: number;
  fps?: number;
}

export interface FrameSetItem {
  folder: string;
  frame_count: number;
  size_bytes: number;
  skip_frames?: number;
  created_at?: number;
  previews: string[];
}

export interface ExtractFramesResponse {
  folder: string;
  saved_frames: number;
  skip_frames: number;
}

export type GridLayoutCount = 1 | 4 | 6;
export type ActivePage = 'live' | 'dataset';
