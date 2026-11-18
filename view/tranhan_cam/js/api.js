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
  config: () => request('GET', '/api/config'),
  cameras: () => request('GET', '/api/cameras'),
  addCamera: (body) => request('POST', '/api/cameras', body),
  updateCamera: (id, body) => request('PUT', `/api/cameras/${id}`, body),
  deleteCamera: (id) => request('DELETE', `/api/cameras/${id}`),
  saveZone: (id, points) => request('PUT', `/api/cameras/${id}/zone`, { points }),
  probeCamera: (id) => request('GET', `/api/cameras/${id}/probe`),

  startRecord: (id, durationMinutes, subtype = 0) =>
    request('POST', `/api/cameras/${id}/record/start`, {
      duration_minutes: durationMinutes,
      subtype,
    }),
  stopRecord: (id) => request('POST', `/api/cameras/${id}/record/stop`),
  activeRecords: () => request('GET', '/api/records/active'),

  listVideos: () => request('GET', '/api/storages/videos'),
  deleteVideo: (filename) => request('DELETE', `/api/storages/videos/${encodeURIComponent(filename)}`),
  extractFrames: (filename, skipFrames) =>
    request('POST', `/api/storages/videos/${encodeURIComponent(filename)}/extract`, {
      skip_frames: skipFrames,
    }),

  listFrameSets: () => request('GET', '/api/storages/frames'),
  deleteFrameSet: (folder) => request('DELETE', `/api/storages/frames/${encodeURIComponent(folder)}`),
};
