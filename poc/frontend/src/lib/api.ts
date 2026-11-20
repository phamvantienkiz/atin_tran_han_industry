import type {
  ActiveRecordJob,
  AppConfig,
  Camera,
  CameraCreatePayload,
  CameraDetection,
  CameraProbeResult,
  CameraUpdatePayload,
  ExtractFramesResponse,
  FrameSetItem,
  VideoItem,
  ZonePoint,
} from '@/types';

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const init: RequestInit = { method, headers };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data?.error?.message) {
        detail = String(data.error.message);
      } else if (data?.detail) {
        detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // keep HTTP status text
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  config: () => request<AppConfig>('GET', '/api/v1/config'),
  cameras: () => request<Camera[]>('GET', '/api/v1/cameras'),
  addCamera: (body: CameraCreatePayload) => request<Camera>('POST', '/api/v1/cameras', body),
  updateCamera: (id: string, body: CameraUpdatePayload) =>
    request<Camera>('PUT', `/api/v1/cameras/${encodeURIComponent(id)}`, body),
  deleteCamera: (id: string) =>
    request<{ status: string; id: string }>('DELETE', `/api/v1/cameras/${encodeURIComponent(id)}`),
  saveZone: (id: string, points: ZonePoint[]) =>
    request<Camera>('PUT', `/api/v1/cameras/${encodeURIComponent(id)}/zone`, { points }),
  probeCamera: (id: string) =>
    request<CameraProbeResult>('GET', `/api/v1/cameras/${encodeURIComponent(id)}/probe`),

  startRecord: (id: string, durationMinutes: number, subtype = 0) =>
    request<ActiveRecordJob>('POST', `/api/v1/cameras/${encodeURIComponent(id)}/record/start`, {
      duration_minutes: durationMinutes,
      subtype,
    }),
  stopRecord: (id: string) =>
    request<{ status: string }>('POST', `/api/v1/cameras/${encodeURIComponent(id)}/record/stop`),
  activeRecords: () => request<ActiveRecordJob[]>('GET', '/api/v1/records/active'),

  listVideos: () => request<VideoItem[]>('GET', '/api/v1/storages/videos'),
  deleteVideo: (filename: string) =>
    request<{ status: string; filename: string }>(
      'DELETE',
      `/api/v1/storages/videos/${encodeURIComponent(filename)}`,
    ),
  extractFrames: (filename: string, skipFrames: number) =>
    request<ExtractFramesResponse>(
      'POST',
      `/api/v1/storages/videos/${encodeURIComponent(filename)}/extract`,
      { skip_frames: skipFrames },
    ),

  listFrameSets: () => request<FrameSetItem[]>('GET', '/api/v1/storages/frames'),
  deleteFrameSet: (folder: string) =>
    request<{ status: string; folder: string }>(
      'DELETE',
      `/api/v1/storages/frames/${encodeURIComponent(folder)}`,
    ),

  detections: (focusCamId: string | null = null) =>
    request<Record<string, CameraDetection>>(
      'GET',
      focusCamId
        ? `/api/v1/detections?focus_cam_id=${encodeURIComponent(focusCamId)}`
        : '/api/v1/detections',
    ),
  setDetectionFocus: (camId: string | null) =>
    request<{ focus_cam_id: string | null }>('POST', '/api/v1/detections/focus', {
      cam_id: camId || null,
    }),
  resetDetectionStats: (camId: string) =>
    request<{ status: string; cam_id: string }>(
      'POST',
      `/api/v1/detections/${encodeURIComponent(camId)}/reset-stats`,
    ),
};
