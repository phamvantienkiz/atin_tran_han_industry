async function request(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      if (data.detail) {
        detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
      }
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  config: () => request('GET', '/api/v1/config'),
  cameras: () => request('GET', '/api/v1/cameras'),
  addCamera: (body) => request('POST', '/api/v1/cameras', body),
  updateCamera: (id, body) => request('PUT', `/api/v1/cameras/${id}`, body),
  deleteCamera: (id) => request('DELETE', `/api/v1/cameras/${id}`),
  saveZone: (id, points) => request('PUT', `/api/v1/cameras/${id}/zone`, { points }),
  probeCamera: (id) => request('GET', `/api/v1/cameras/${id}/probe`),

  startRecord: (id, durationMinutes, subtype = 0) =>
    request('POST', `/api/v1/cameras/${id}/record/start`, {
      duration_minutes: durationMinutes,
      subtype,
    }),
  stopRecord: (id) => request('POST', `/api/v1/cameras/${id}/record/stop`),
  activeRecords: () => request('GET', '/api/v1/records/active'),

  listVideos: () => request('GET', '/api/v1/storages/videos'),
  deleteVideo: (filename) => request('DELETE', `/api/v1/storages/videos/${encodeURIComponent(filename)}`),
  extractFrames: (filename, skipFrames) =>
    request('POST', `/api/v1/storages/videos/${encodeURIComponent(filename)}/extract`, {
      skip_frames: skipFrames,
    }),

  listFrameSets: () => request('GET', '/api/v1/storages/frames'),
  deleteFrameSet: (folder) => request('DELETE', `/api/v1/storages/frames/${encodeURIComponent(folder)}`),
  detections: (focusCamId = null) =>
    request(
      'GET',
      focusCamId ? `/api/v1/detections?focus_cam_id=${encodeURIComponent(focusCamId)}` : '/api/v1/detections'
    ),
  setDetectionFocus: (camId) =>
    request('POST', '/api/v1/detections/focus', { cam_id: camId || null }),
};
